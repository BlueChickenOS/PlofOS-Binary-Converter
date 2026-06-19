import numpy as np
import sounddevice as sd
import soundfile as sf
import os
import time
import socket
import threading
import json
import struct

# -- ANSI COLORS ---------------------------------------------------------------

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    DIM    = "\033[2m"

def cprint(text, color=C.RESET, delay=0.02):
    try:
        print(color + text + C.RESET)
    except UnicodeEncodeError:
        print(color + text.encode("ascii", errors="replace").decode() + C.RESET)
    time.sleep(delay)

def slow_print(text, color=C.RESET, char_delay=0.015):
    print(color, end="", flush=True)
    for char in text:
        try:
            print(char, end="", flush=True)
        except UnicodeEncodeError:
            print("?", end="", flush=True)
        time.sleep(char_delay)
    print(C.RESET, flush=True)  # always end with newline so GUI reader flushes

def divider(color=C.CYAN):
    cprint("  " + "-" * 41, color, delay=0.03)

# -- SETTINGS FILE -------------------------------------------------------------
# settings.txt lives next to the EXE/BAT file.
# sys.executable points to the EXE when bundled, __file__ when run as script.

import sys

def get_script_dir():
    """Get the folder where the EXE or script lives."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller EXE
        return os.path.dirname(sys.executable)
    else:
        # Running as .py script
        return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR    = get_script_dir()
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.txt")

DEFAULT_SETTINGS_CONTENT = """\
# BinarySoundConverter -- Settings File
# Lines starting with # are comments and are ignored.
# Delete this file to reset all settings to defaults.

# -- OUTPUT / INPUT FOLDERS ----------------------------------------------------
# Full path to the main output folder. Subfolders are created automatically.
# Leave blank to use the folder next to the EXE/script.
output_folder=

# Full path to the inbox (Infiles) folder.
# Leave blank to use output_folder/Infiles
infiles_folder=

# -- LOG FILE ------------------------------------------------------------------
# Full path to the log file. Leave blank to place it next to the EXE/script.
# Log rotates automatically when it reaches 10 MB.
log_file=

# -- AUDIO SETTINGS ------------------------------------------------------------
freq_zero=440
freq_one=880
tone_duration=0.01
volume=0.5

# -- HEADER BLOCK SETTINGS -----------------------------------------------------
header_freq_zero=300
header_freq_one=600
header_tone_duration=0.05

# -- ROW MODE ------------------------------------------------------------------
# Row mode splits encoding into 3 rows of frequencies, rotating every 8 bits.
# Configure via Settings -> Row Mode inside the app.
# These are saved here automatically when you set them in the app.
row_mode=false
row1_freq_zero=400
row1_freq_one=800
row2_freq_zero=500
row2_freq_one=900
row3_freq_zero=600
row3_freq_one=1000

# -- LOCKS ---------------------------------------------------------------------
# true = locked (cannot be changed inside the app)
lock_freq_zero=false
lock_freq_one=false
lock_tone_duration=false
lock_volume=false
"""

SAMPLE_RATE = 44100
SETTINGS = {
    "freq_zero":     440,
    "freq_one":      880,
    "tone_duration": 0.01,
    "volume":        0.5,
    "row_mode":      False,
    "rows": [
        {"freq_zero": 440, "freq_one": 880},
        {"freq_zero": 440, "freq_one": 880},
        {"freq_zero": 440, "freq_one": 880},
    ],
    "lock_freq_zero":     False,
    "lock_freq_one":      False,
    "lock_tone_duration": False,
    "lock_volume":        False,
    "header_freq_zero":     300,
    "header_freq_one":      600,
    "header_tone_duration": 0.05,
}

SETTINGS_ERRORS   = []  # collected at startup, shown to user

def parse_settings_file():
    """Read settings.txt and apply values. Collect errors without crashing."""
    global SETTINGS_ERRORS

    if not os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                f.write(DEFAULT_SETTINGS_CONTENT)
        except Exception as e:
            SETTINGS_ERRORS.append(f"Could not create settings.txt: {e}")
        return {}, "", ""

    values   = {}
    errors   = []
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        SETTINGS_ERRORS.append(f"Could not read settings.txt: {e}")
        return {}, "", ""

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f"  Line {i}: missing '=' -- '{line}'")
            continue
        key, _, val = line.partition("=")
        key = key.strip().lower()
        val = val.strip()
        values[key] = val

    SETTINGS_ERRORS.extend(errors)
    out_folder     = values.get("output_folder", "")
    infiles_folder = values.get("infiles_folder", "")
    log_file       = values.get("log_file", "")
    return values, out_folder, infiles_folder, log_file

def apply_settings_file(values):
    """Apply parsed settings values to SETTINGS dict."""
    float_keys = {
        "freq_zero":     ("freq_zero",     100,  5000),
        "freq_one":      ("freq_one",      100,  5000),
        "tone_duration": ("tone_duration", 0.005, 2.0),
        "volume":        ("volume",        0.0,   1.0),
        "header_freq_zero":     ("header_freq_zero",     100, 5000),
        "header_freq_one":      ("header_freq_one",      100, 5000),
        "header_tone_duration": ("header_tone_duration", 0.005, 2.0),
    }
    bool_keys = ["lock_freq_zero", "lock_freq_one", "lock_tone_duration", "lock_volume"]

    for file_key, (setting_key, mn, mx) in float_keys.items():
        if file_key in values and values[file_key] != "":
            try:
                val = float(values[file_key])
                if mn <= val <= mx:
                    SETTINGS[setting_key] = val
                else:
                    SETTINGS_ERRORS.append(
                        f"  settings.txt: '{file_key}={values[file_key]}' out of range ({mn}-{mx}), using default.")
            except ValueError:
                SETTINGS_ERRORS.append(
                    f"  settings.txt: '{file_key}={values[file_key]}' is not a number, using default.")

    for key in bool_keys:
        if key in values:
            val = values[key].lower()
            if val in ("true", "false"):
                SETTINGS[key] = (val == "true")
            else:
                SETTINGS_ERRORS.append(
                    f"  settings.txt: '{key}={values[key]}' must be true or false, using default.")

    # Row mode
    if "row_mode" in values:
        SETTINGS["row_mode"] = values["row_mode"].lower() == "true"

    row_float_keys = {
        "row1_freq_zero": (0, "freq_zero"), "row1_freq_one": (0, "freq_one"),
        "row2_freq_zero": (1, "freq_zero"), "row2_freq_one": (1, "freq_one"),
        "row3_freq_zero": (2, "freq_zero"), "row3_freq_one": (2, "freq_one"),
    }
    for file_key, (row_idx, sub_key) in row_float_keys.items():
        if file_key in values and values[file_key] != "":
            try:
                val = float(values[file_key])
                if 100 <= val <= 5000:
                    SETTINGS["rows"][row_idx][sub_key] = val
                else:
                    SETTINGS_ERRORS.append(
                        f"  settings.txt: '{file_key}' out of range (100-5000), using default.")
            except ValueError:
                SETTINGS_ERRORS.append(
                    f"  settings.txt: '{file_key}' is not a number, using default.")

# -- FOLDER SETUP --------------------------------------------------------------

BASE_DIR     = SCRIPT_DIR  # updated properly in main() after settings load
INFILES_DIR  = os.path.join(BASE_DIR, "Infiles")
AUDIO_DIR    = os.path.join(BASE_DIR, "Audio")
TXT_DIR      = os.path.join(BASE_DIR, "TextFiles")
FILES_DIR    = os.path.join(BASE_DIR, "RebuiltFiles")
KEYS_DIR     = os.path.join(BASE_DIR, "Keys")

def update_dirs(new_base, new_infiles=""):
    global BASE_DIR, INFILES_DIR, AUDIO_DIR, TXT_DIR, FILES_DIR, KEYS_DIR
    BASE_DIR    = new_base
    INFILES_DIR = new_infiles if new_infiles else os.path.join(BASE_DIR, "Infiles")
    AUDIO_DIR   = os.path.join(BASE_DIR, "Audio")
    TXT_DIR     = os.path.join(BASE_DIR, "TextFiles")
    FILES_DIR   = os.path.join(BASE_DIR, "RebuiltFiles")
    KEYS_DIR    = os.path.join(BASE_DIR, "Keys")
    setup_folders()

def setup_folders():
    for folder in [BASE_DIR, INFILES_DIR, AUDIO_DIR, TXT_DIR, FILES_DIR, KEYS_DIR]:
        os.makedirs(folder, exist_ok=True)

def audio_path(fn):   return os.path.join(AUDIO_DIR,  fn)
def txt_path(fn):     return os.path.join(TXT_DIR,    fn)
def files_path(fn):   return os.path.join(FILES_DIR,  fn)
def keys_path(fn):    return os.path.join(KEYS_DIR,   fn)

# -- LOGGING -------------------------------------------------------------------

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_FILE      = os.path.join(SCRIPT_DIR, "bsc_log.txt")

def set_log_file(path):
    global LOG_FILE
    LOG_FILE = path

def log(action, detail=""):
    """Append a log entry. Rotates file if over 10 MB."""
    try:
        # Rotate if over limit
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) >= LOG_MAX_BYTES:
            old = LOG_FILE.replace(".txt", "_old.txt")
            if os.path.exists(old):
                os.remove(old)
            os.rename(LOG_FILE, old)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {action}"
        if detail:
            line += f" | {detail}"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # Never crash due to logging

def logaction(action):
    """Log a user action (menu choices, file operations, etc.)"""
    log(f"ACTION | {action}")
# ==============================================================================
#
#  Discovery  : UDP broadcast on port 55400, peers announce themselves
#  Transfer   : TCP on port 55401, sender pushes a JSON packet
#  Packet types: "binary" (raw 0s/1s text) or "wav" (base64-encoded WAV bytes)

ONLINE_PORT_DISC  = 55400   # UDP discovery
ONLINE_PORT_DATA  = 55401   # TCP data transfer
ONLINE_APP_ID     = "BSC_PLOFOS_V1"
ONLINE_STATE      = {
    "active":      False,
    "peers":       {},      # {ip: {"label": "Peer 1", "last_seen": time}}
    "peer_counter": 0,      # increments each time a new peer is discovered
    "disc_thread":  None,
    "recv_thread":  None,
    "inbox":       [],      # received packets waiting to be handled
    "inbox_lock":  threading.Lock(),
}

def _peer_display(ip):
    """Return display name for a peer IP."""
    peer = ONLINE_STATE["peers"].get(ip, {})
    label     = peer.get("label", ip)
    call_name = peer.get("call_name")
    return f"{call_name}  [{label}]" if call_name else label

def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def _get_hostname():
    try:
        return socket.gethostname()
    except Exception:
        return "Unknown"

# -- DISCOVERY (UDP broadcast) -------------------------------------------------

def _discovery_loop():
    """Broadcast presence and listen for others on UDP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", ONLINE_PORT_DISC))
    except Exception as e:
        log("Online mode discovery bind failed", str(e))
        return
    sock.settimeout(1.0)

    local_ip   = _get_local_ip()
    hostname   = _get_hostname()
    announce   = json.dumps({
        "app": ONLINE_APP_ID,
        "name": hostname,
        "ip": local_ip,
    }).encode("utf-8")

    last_broadcast = 0
    while ONLINE_STATE["active"]:
        # Broadcast every 3 seconds
        if time.time() - last_broadcast > 3:
            try:
                sock.sendto(announce, ("<broadcast>", ONLINE_PORT_DISC))
            except Exception:
                pass
            last_broadcast = time.time()

        # Listen for peers
        try:
            data, addr = sock.recvfrom(1024)
            msg = json.loads(data.decode("utf-8"))
            if msg.get("app") == ONLINE_APP_ID and addr[0] != local_ip:
                if addr[0] not in ONLINE_STATE["peers"]:
                    # New peer — assign next label
                    ONLINE_STATE["peer_counter"] += 1
                    label = f"Peer {ONLINE_STATE['peer_counter']}"
                    ONLINE_STATE["peers"][addr[0]] = {
                        "label":      label,
                        "last_seen":  time.time(),
                        "call_name":  None,
                    }
                    log("Peer discovered", f"{label} at {addr[0]}")
                else:
                    # Known peer — just refresh timestamp, never reassign label
                    ONLINE_STATE["peers"][addr[0]]["last_seen"] = time.time()
        except socket.timeout:
            pass
        except Exception:
            pass

        # Prune peers not seen in 30 seconds (increased from 10 to avoid flicker)
        now = time.time()
        lost = [ip for ip, p in ONLINE_STATE["peers"].items()
                if now - p["last_seen"] > 30]
        for ip in lost:
            label = ONLINE_STATE["peers"][ip].get("label", ip)
            del ONLINE_STATE["peers"][ip]
            log("Peer lost", f"{label} at {ip}")

    sock.close()

# -- RECEIVER (TCP) ------------------------------------------------------------

def _receiver_loop():
    """Listen for incoming TCP packets."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("", ONLINE_PORT_DATA))
        server.listen(5)
    except Exception as e:
        log("Online mode receiver bind failed", str(e))
        return
    server.settimeout(1.0)

    while ONLINE_STATE["active"]:
        try:
            conn, addr = server.accept()
            threading.Thread(
                target=_handle_incoming,
                args=(conn, addr),
                daemon=True
            ).start()
        except socket.timeout:
            pass
        except Exception:
            pass

    server.close()

def _handle_incoming(conn, addr):
    """Read a length-prefixed JSON packet from a peer."""
    try:
        # First 4 bytes = packet length
        raw_len = _recv_exact(conn, 4)
        if not raw_len:
            return
        packet_len = struct.unpack(">I", raw_len)[0]
        raw_data   = _recv_exact(conn, packet_len)
        if not raw_data:
            return
        packet = json.loads(raw_data.decode("utf-8"))
        packet["from_ip"]   = addr[0]
        packet["from_name"] = ONLINE_STATE["peers"].get(addr[0], {}).get("name", addr[0])
        with ONLINE_STATE["inbox_lock"]:
            ONLINE_STATE["inbox"].append(packet)
        log("Received network packet", f"from={addr[0]} type={packet.get('type')}")
    except Exception as e:
        log("Error handling incoming packet", str(e))
    finally:
        conn.close()

def _recv_exact(conn, n):
    """Read exactly n bytes from a socket."""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

# -- SENDER (TCP) --------------------------------------------------------------

def _send_packet(ip, packet):
    """Send a length-prefixed JSON packet to a peer."""
    try:
        raw  = json.dumps(packet).encode("utf-8")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((ip, ONLINE_PORT_DATA))
        sock.sendall(struct.pack(">I", len(raw)) + raw)
        sock.close()
        return True
    except Exception as e:
        cprint(f"  Error sending to {ip}: {e}", C.RED)
        log("Send error", f"{ip}: {e}")
        return False

def _send_to_peers(packet, target_ip=None):
    """Send packet to one or all peers."""
    peers = {target_ip: ONLINE_STATE["peers"][target_ip]} \
        if target_ip else ONLINE_STATE["peers"]

    if not peers:
        cprint("  No peers found on the network.", C.YELLOW)
        return 0

    success = 0
    for ip, info in peers.items():
        label = info.get("label", info.get("name", ip))
        cprint(f"  Sending to {label} ({ip})...", C.DIM, delay=0)
        if _send_packet(ip, packet):
            cprint(f"  Sent to {label}!", C.GREEN, delay=0)
            success += 1
    return success

# -- ONLINE MODE CONTROL -------------------------------------------------------

def start_online_mode():
    if ONLINE_STATE["active"]:
        cprint("  Online mode is already active.", C.YELLOW)
        return

    ONLINE_STATE["active"] = True
    ONLINE_STATE["peers"]  = {}
    ONLINE_STATE["inbox"]  = []

    ONLINE_STATE["disc_thread"] = threading.Thread(
        target=_discovery_loop, daemon=True)
    ONLINE_STATE["recv_thread"] = threading.Thread(
        target=_receiver_loop,  daemon=True)

    ONLINE_STATE["disc_thread"].start()
    ONLINE_STATE["recv_thread"].start()

    cprint(f"\n  Online mode started!", C.GREEN + C.BOLD)
    cprint(f"  Your name : {_get_hostname()}", C.CYAN)
    cprint(f"  Your IP   : {_get_local_ip()}", C.CYAN)
    cprint(f"  Listening for peers...", C.DIM)
    log("Online mode started", _get_local_ip())

def stop_online_mode():
    ONLINE_STATE["active"] = False
    cprint("  Online mode stopped.", C.YELLOW)
    log("Online mode stopped")

# -- INBOX HANDLER -------------------------------------------------------------

def check_inbox():
    """Process any received packets -- call this at the start of menus."""
    with ONLINE_STATE["inbox_lock"]:
        if not ONLINE_STATE["inbox"]:
            return
        packets = list(ONLINE_STATE["inbox"])
        ONLINE_STATE["inbox"].clear()

    for packet in packets:
        _handle_packet(packet)

def _handle_packet(packet):
    """Show a received packet and ask what to do with it."""
    ptype    = packet.get("type", "unknown")
    from_ip  = packet.get("from_ip", "?")
    from_name = _peer_display(from_ip)

    # -- Call ID request -- someone is asking for your name ---------------------
    if ptype == "call_id_request":
        cprint("\n" + "=" * 45, C.YELLOW)
        cprint(f"  CALL ID REQUEST from {from_name} ({from_ip})", C.YELLOW + C.BOLD)
        cprint("=" * 45, C.YELLOW)
        cprint("  They want to know your short name (max 20 chars).", C.DIM)
        name = input(f"  {C.YELLOW}Your name{C.RESET}: ").strip()[:20]
        if not name:
            name = _get_hostname()[:20]
        reply = {"type": "call_id_reply", "name": name, "from": _get_hostname()}
        if _send_packet(from_ip, reply):
            cprint(f"  Sent your name '{name}' back.", C.GREEN)
            log("Call ID reply sent", f"name={name} to={from_ip}")
        return

    # -- Call ID reply -- someone responded with their name ---------------------
    if ptype == "call_id_reply":
        name = packet.get("name", "?")
        cprint("\n" + "=" * 45, C.GREEN)
        cprint(f"  CALL ID REPLY from {from_name}", C.GREEN + C.BOLD)
        cprint("=" * 45, C.GREEN)
        cprint(f"  Their chosen name: {C.WHITE}{name}{C.RESET}", delay=0.05)
        if from_ip in ONLINE_STATE["peers"]:
            ONLINE_STATE["peers"][from_ip]["call_name"] = name
        log("Call ID received", f"name={name} from={from_ip} ({from_name})")
        return

    # -- All other packet types show the incoming header ------------------------
    cprint("\n" + "=" * 45, C.YELLOW)
    cprint(f"  INCOMING from {from_name} ({from_ip})", C.YELLOW + C.BOLD)
    cprint("=" * 45, C.YELLOW)

    if ptype == "binary":
        binary = packet.get("data", "")
        cprint(f"  Type   : Binary ({len(binary)} bits)", C.CYAN)
        if len(binary) <= 200:
            cprint(f"  Data   : {binary}", C.WHITE)
        else:
            cprint(f"  Data   : (too long to display -- {len(binary)} bits)", C.DIM)

        action = input(
            f"\n  {C.CYAN}1{C.RESET} Save as TXT  "
            f"{C.CYAN}2{C.RESET} Convert to WAV  "
            f"{C.CYAN}3{C.RESET} Discard: "
        ).strip()

        if action == "1":
            fn = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or f"received_from_{from_name}"
            save_binary_txt(binary, fn)
            cprint("  Saved to TextFiles folder.", C.GREEN + C.BOLD)
        elif action == "2":
            fn = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or f"received_from_{from_name}"
            save_audio_files(binary, fn)
            cprint("  Saved to Audio folder.", C.GREEN + C.BOLD)
        else:
            logaction("Received packet: discarded"); cprint("  Discarded.", C.DIM)

    elif ptype == "wav":
        import base64
        wav_data  = base64.b64decode(packet.get("data", ""))
        orig_name = packet.get("filename", "received.wav")
        cprint(f"  Type   : WAV file ({len(wav_data):,} bytes)", C.CYAN)
        cprint(f"  Name   : {orig_name}", C.CYAN)

        action = input(
            f"\n  {C.CYAN}1{C.RESET} Save WAV  "
            f"{C.CYAN}2{C.RESET} Save WAV + decode binary  "
            f"{C.CYAN}3{C.RESET} Discard: "
        ).strip()

        if action in ("1", "2"):
            fn     = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or f"received_from_{from_name}"
            wav_fp = audio_path(fn + ".wav")
            try:
                with open(wav_fp, "wb") as f:
                    f.write(wav_data)
                cprint(f"  WAV saved: {wav_fp}", C.GREEN)
                log("Received WAV saved", f"path={wav_fp}")
                if action == "2":
                    result = decode_wav_file(wav_fp)
                    if result:
                        output_binary(result)
            except Exception as e:
                cprint(f"  Error saving WAV: {e}", C.RED)
        else:
            cprint("  Discarded.", C.DIM)

    elif ptype == "message":
        msg_text  = packet.get("data", "")
        cprint("\n" + "=" * 45, C.CYAN)
        cprint(f"  MESSAGE from {from_name}", C.CYAN + C.BOLD)
        cprint("=" * 45, C.CYAN)
        cprint(f"  {msg_text}", C.WHITE)
        cprint("", C.RESET, delay=0.05)
        log("Received text message", f"from={from_ip} | msg={msg_text[:80]}")
        return

    elif ptype == "txt":
        import base64
        txt_data  = base64.b64decode(packet.get("data", "")).decode("utf-8", errors="replace")
        orig_name = packet.get("filename", "received.txt")
        cprint(f"  Type   : TXT file ({len(txt_data)} chars)", C.CYAN)
        cprint(f"  Name   : {orig_name}", C.CYAN)

        # Preview first 5 lines
        preview_lines = txt_data.splitlines()[:5]
        cprint(f"\n  Preview:", C.DIM)
        for line in preview_lines:
            cprint(f"    {line[:60]}", C.WHITE, delay=0.01)
        if len(txt_data.splitlines()) > 5:
            cprint(f"    ... ({len(txt_data.splitlines())} lines total)", C.DIM)

        action = input(
            f"\n  {C.CYAN}1{C.RESET} Save TXT  "
            f"{C.CYAN}2{C.RESET} Save TXT + decode as binary  "
            f"{C.CYAN}3{C.RESET} Discard: "
        ).strip()

        if action in ("1", "2"):
            fn      = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or f"received_from_{from_name}"
            txt_fp  = txt_path(fn + ".txt")
            try:
                with open(txt_fp, "w", encoding="utf-8") as f:
                    f.write(txt_data)
                cprint(f"  TXT saved: {txt_fp}", C.GREEN)
                log("Received TXT saved", f"path={txt_fp}")
                if action == "2":
                    binary = validate_binary_input(txt_data)
                    if binary:
                        output_binary(binary)
                    else:
                        cprint("  File does not contain valid binary data.", C.YELLOW)
            except Exception as e:
                cprint(f"  Error saving TXT: {e}", C.RED)
        else:
            cprint("  Discarded.", C.DIM)

    else:
        cprint(f"  Unknown packet type: {ptype}", C.RED)

# -- ONLINE MENU ---------------------------------------------------------------

def menu_online():
    while True:
        if ONLINE_STATE["active"]:
            check_inbox()

        time.sleep(0.1)
        divider(C.YELLOW)
        status = (C.GREEN + "ONLINE" + C.RESET) if ONLINE_STATE["active"] \
                 else (C.RED + "OFFLINE" + C.RESET)
        cprint(f"    ONLINE MODE  [{status}]", C.YELLOW + C.BOLD)
        divider(C.YELLOW)

        if ONLINE_STATE["active"]:
            peers = ONLINE_STATE["peers"]
            if peers:
                cprint(f"  Peers found: {len(peers)}", C.CYAN, delay=0.02)
                for i, (ip, info) in enumerate(peers.items(), 1):
                    call_name = info.get("call_name", "")
                    label     = info.get("label", ip)
                    display   = f"{call_name}  [{label}]" if call_name else label
                    cprint(f"    {C.CYAN}{i}{C.RESET}. {display}", C.DIM, delay=0.02)
            else:
                cprint("  No peers found yet...", C.DIM)

        cprint(f"  {C.YELLOW}1{C.RESET} - {'Stop' if ONLINE_STATE['active'] else 'Start'} online mode", delay=0.03)
        if ONLINE_STATE["active"]:
            cprint(f"  {C.YELLOW}2{C.RESET} - Send binary to all peers",    delay=0.03)
            cprint(f"  {C.YELLOW}3{C.RESET} - Send binary to one peer",     delay=0.03)
            cprint(f"  {C.YELLOW}4{C.RESET} - Send WAV to all peers",       delay=0.03)
            cprint(f"  {C.YELLOW}5{C.RESET} - Send WAV to one peer",        delay=0.03)
            cprint(f"  {C.YELLOW}6{C.RESET} - Send TXT file to all peers",  delay=0.03)
            cprint(f"  {C.YELLOW}7{C.RESET} - Send TXT file to one peer",   delay=0.03)
            cprint(f"  {C.YELLOW}8{C.RESET} - Call ID (ask peer for name)", delay=0.03)
            cprint(f"  {C.YELLOW}9{C.RESET} - Check inbox",                 delay=0.03)
            cprint(f"  {C.YELLOW}m{C.RESET} - Send text message to all peers", delay=0.03)
            cprint(f"  {C.YELLOW}p{C.RESET} - Send text message to one peer",  delay=0.03)
            cprint(f"  {C.YELLOW}d{C.RESET} - Delete a peer from the list",        delay=0.03)
            cprint(f"  {C.YELLOW}r{C.RESET} - Refresh peer list",                   delay=0.03)
        cprint(f"  {C.YELLOW}0{C.RESET} - Back to main menu", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip().lower()

        if choice == "0":
            break
        elif _check_scram(choice): pass
        elif choice == "1":
            if ONLINE_STATE["active"]:
                stop_online_mode()
            else:
                start_online_mode()
        elif choice == "2" and ONLINE_STATE["active"]:
            logaction("Online: Send binary to all"); _online_send_binary()
        elif choice == "3" and ONLINE_STATE["active"]:
            logaction("Online: Send binary to one peer"); _online_send_binary(pick_peer=True)
        elif choice == "4" and ONLINE_STATE["active"]:
            logaction("Online: Send WAV to all"); _online_send_wav()
        elif choice == "5" and ONLINE_STATE["active"]:
            logaction("Online: Send WAV to one peer"); _online_send_wav(pick_peer=True)
        elif choice == "6" and ONLINE_STATE["active"]:
            logaction("Online: Send TXT to all"); _online_send_txt()
        elif choice == "7" and ONLINE_STATE["active"]:
            logaction("Online: Send TXT to one peer"); _online_send_txt(pick_peer=True)
        elif choice == "8" and ONLINE_STATE["active"]:
            logaction("Online: Call ID request"); _online_call_id()
        elif choice == "9" and ONLINE_STATE["active"]:
            with ONLINE_STATE["inbox_lock"]:
                has = bool(ONLINE_STATE["inbox"])
            if has:
                check_inbox()
            else:
                cprint("  No new messages.", C.DIM)
        elif choice == "m" and ONLINE_STATE["active"]:
            logaction("Online: Send text to all"); _online_send_message()
        elif choice == "p" and ONLINE_STATE["active"]:
            logaction("Online: Send text to one peer"); _online_send_message(pick_peer=True)
        elif choice == "d" and ONLINE_STATE["active"]:
            _online_delete_peer()
        elif choice == "r" and ONLINE_STATE["active"]:
            cprint("  Refreshing...", C.DIM)
            time.sleep(2)
        else:
            cprint("  Invalid choice.", C.RED)

def _pick_peer():
    """Let the user pick a single peer. Returns IP or None."""
    peers = ONLINE_STATE["peers"]
    if not peers:
        cprint("  No peers found on the network.", C.YELLOW)
        return None

    cprint("\n  Available peers:", C.CYAN)
    peer_list = list(peers.items())
    for i, (ip, info) in enumerate(peer_list, 1):
        cprint(f"  {C.CYAN}{i}{C.RESET} - {_peer_display(ip)}", delay=0.02)

    try:
        idx = int(input(f"  {C.YELLOW}Pick a number{C.RESET}: ").strip()) - 1
        if 0 <= idx < len(peer_list):
            return peer_list[idx][0]
        cprint("  Invalid choice.", C.RED)
    except ValueError:
        cprint("  Please enter a number.", C.RED)
    return None

def _online_send_binary(pick_peer=False):
    cprint(f"\n  Enter the binary to send:", C.CYAN)
    binary = validate_binary_input(
        input(f"  {C.YELLOW}Binary (0s and 1s){C.RESET}: "))
    if not binary:
        return

    target = _pick_peer() if pick_peer else None
    if pick_peer and target is None:
        return

    packet = {"type": "binary", "data": binary,
               "from": _get_hostname()}
    n = _send_to_peers(packet, target_ip=target)
    if n:
        cprint(f"\n  Sent to {n} peer(s).", C.GREEN + C.BOLD)
        log("Sent binary over network", f"{len(binary)} bits to {target or 'all'}")

def _online_send_wav(pick_peer=False):
    import base64
    fp = input(f"\n  {C.YELLOW}Path to WAV file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED)
        return

    size = os.path.getsize(fp)
    if size > 50 * 1024 * 1024:
        cprint("  Error: WAV file is larger than 50 MB. Please use a smaller file.", C.RED)
        return

    cprint(f"  Reading {size/1024:.1f} KB...", C.DIM)
    try:
        with open(fp, "rb") as f:
            wav_bytes = f.read()
    except Exception as e:
        cprint(f"  Error reading file: {e}", C.RED)
        return

    target = _pick_peer() if pick_peer else None
    if pick_peer and target is None:
        return

    packet = {
        "type":     "wav",
        "data":     base64.b64encode(wav_bytes).decode("utf-8"),
        "filename": os.path.basename(fp),
        "from":     _get_hostname(),
    }
    cprint("  Sending (this may take a moment for large files)...", C.DIM)
    n = _send_to_peers(packet, target_ip=target)
    if n:
        cprint(f"\n  Sent to {n} peer(s).", C.GREEN + C.BOLD)
        log("Sent WAV over network", f"path={fp} | to={target or 'all'}")

def _online_send_txt(pick_peer=False):
    import base64
    fp = input(f"\n  {C.YELLOW}Path to TXT file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED)
        return
    if not fp.lower().endswith(".txt"):
        cprint("  Error: Only .txt files can be sent with this option.", C.RED)
        return

    size = os.path.getsize(fp)
    if size > 10 * 1024 * 1024:
        cprint("  Error: TXT file is larger than 10 MB.", C.RED)
        return

    try:
        with open(fp, "r", encoding="utf-8") as f:
            txt_data = f.read()
    except Exception as e:
        cprint(f"  Error reading file: {e}", C.RED)
        return

    target = _pick_peer() if pick_peer else None
    if pick_peer and target is None:
        return

    packet = {
        "type":     "txt",
        "data":     base64.b64encode(txt_data.encode("utf-8")).decode("utf-8"),
        "filename": os.path.basename(fp),
        "from":     _get_hostname(),
    }
    n = _send_to_peers(packet, target_ip=target)
    if n:
        cprint(f"\n  Sent to {n} peer(s).", C.GREEN + C.BOLD)
        log("Sent TXT over network", f"path={fp} | to={target or 'all'}")

def _online_send_message(pick_peer=False):
    """Send a plain text message to peers."""
    cprint(f"\n  Type your message:", C.CYAN)
    msg = input(f"  {C.YELLOW}Message{C.RESET}: ").strip()
    if not msg:
        cprint("  Nothing sent.", C.DIM)
        return

    target = _pick_peer() if pick_peer else None
    if pick_peer and target is None:
        return

    packet = {
        "type": "message",
        "data": msg,
        "from": _get_hostname(),
    }
    n = _send_to_peers(packet, target_ip=target)
    if n:
        cprint(f"\n  Message sent to {n} peer(s).", C.GREEN + C.BOLD)
        log("Sent text message", f"msg={msg[:80]} | to={target or 'all'}")


def _online_call_id():
    """Send a call ID request to a chosen peer."""
    peers = ONLINE_STATE["peers"]
    if not peers:
        cprint("  No peers found on the network.", C.YELLOW)
        return

    cprint("\n  Who do you want to call ID?", C.CYAN)
    peer_list = list(peers.items())
    for i, (ip, info) in enumerate(peer_list, 1):
        cprint(f"  {C.CYAN}{i}{C.RESET} - {_peer_display(ip)}", delay=0.02)

    try:
        idx = int(input(f"  {C.YELLOW}Pick a number{C.RESET}: ").strip()) - 1
        if not (0 <= idx < len(peer_list)):
            cprint("  Invalid choice.", C.RED)
            return
    except ValueError:
        cprint("  Please enter a number.", C.RED)
        return

    target_ip = peer_list[idx][0]
    label     = _peer_display(target_ip)
    packet    = {"type": "call_id_request", "from": _get_hostname()}
    cprint(f"  Sending Call ID request to {label}...", C.DIM)
    if _send_packet(target_ip, packet):
        cprint(f"  Request sent! Waiting for {label} to respond...", C.YELLOW)
        cprint("  Their chosen name will appear when they reply.", C.DIM)
        log("Call ID request sent", f"to {label} ({target_ip})")

def _online_delete_peer():
    """Manually remove a peer from the list."""
    peers = ONLINE_STATE["peers"]
    if not peers:
        cprint("  No peers to delete.", C.YELLOW)
        return

    cprint("\n  Which peer do you want to remove?", C.CYAN)
    peer_list = list(peers.items())
    for i, (ip, info) in enumerate(peer_list, 1):
        cprint(f"  {C.CYAN}{i}{C.RESET} - {_peer_display(ip)}", delay=0.02)
    cprint(f"  {C.CYAN}0{C.RESET} - Cancel", delay=0.02)

    try:
        idx = int(input(f"  {C.YELLOW}Pick a number{C.RESET}: ").strip()) - 1
        if idx == -1:
            return
        if not (0 <= idx < len(peer_list)):
            cprint("  Invalid choice.", C.RED)
            return
    except ValueError:
        cprint("  Please enter a number.", C.RED)
        return

    ip, info = peer_list[idx]
    label    = _peer_display(ip)
    del ONLINE_STATE["peers"][ip]
    cprint(f"\n  Removed {label} from the list.", C.GREEN)
    log("Peer manually removed", f"{label} ({ip})")

# -- END ONLINE MODE -----------------------------------------------------------

# -- SHARED AUDIO HELPERS ------------------------------------------------------

def ask_float(label, default, min_val, max_val):
    while True:
        raw = input(f"  {C.YELLOW}{label} (default {default}){C.RESET}: ").strip()
        if raw == "":
            return default
        try:
            val = float(raw)
            if min_val <= val <= max_val:
                return val
            cprint(f"    Please enter a value between {min_val} and {max_val}.", C.RED)
        except ValueError:
            cprint("    Please enter a valid number.", C.RED)

def make_tone(frequency, duration):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return SETTINGS["volume"] * np.sin(2 * np.pi * frequency * t).astype(np.float32)

def make_tone_raw(frequency, duration, volume=0.5):
    """Make a tone with explicit volume, used for header encoding."""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return volume * np.sin(2 * np.pi * frequency * t).astype(np.float32)

def detect_bit(chunk, sample_rate, freq_zero, freq_one, tolerance=None):
    if tolerance is None:
        tolerance = max(80, int(1.0 / SETTINGS["tone_duration"]) * 2)
    fft      = np.fft.rfft(chunk)
    freqs    = np.fft.rfftfreq(len(chunk), 1 / sample_rate)
    dominant = freqs[np.argmax(np.abs(fft))]
    d0 = abs(dominant - freq_zero)
    d1 = abs(dominant - freq_one)
    if d0 > tolerance and d1 > tolerance:
        return None
    return "0" if d0 < d1 else "1"

def get_row_freqs(bit_index):
    if SETTINGS["row_mode"]:
        row = (bit_index // 8) % 3
        return SETTINGS["rows"][row]["freq_zero"], SETTINGS["rows"][row]["freq_one"]
    return SETTINGS["freq_zero"], SETTINGS["freq_one"]

def save_wav_chunked(binary, wav_filepath, freq_zero=None, freq_one=None,
                     tone_dur=None, volume=None):
    """Write WAV in chunks. Uses session settings unless overrides provided."""
    fz       = freq_zero  if freq_zero  is not None else None
    fo       = freq_one   if freq_one   is not None else None
    dur      = tone_dur   if tone_dur   is not None else SETTINGS["tone_duration"]
    vol      = volume     if volume     is not None else SETTINGS["volume"]
    override = (fz is not None)

    CHUNK_BITS  = 1000
    total_bits  = len(binary)
    samples_per = int(dur * SAMPLE_RATE)
    done        = 0
    last_pct    = -1

    with sf.SoundFile(wav_filepath, mode='w', samplerate=SAMPLE_RATE,
                      channels=1, subtype='FLOAT') as wav:
        while done < total_bits:
            chunk_bits  = binary[done:done + CHUNK_BITS]
            chunk_audio = []
            for i, bit in enumerate(chunk_bits):
                if override:
                    freq = fo if bit == "1" else fz
                else:
                    rfz, rfo = get_row_freqs(done + i)
                    freq = rfo if bit == "1" else rfz
                t    = np.linspace(0, dur, samples_per, endpoint=False)
                tone = vol * np.sin(2 * np.pi * freq * t).astype(np.float32)
                chunk_audio.append(tone)
            wav.write(np.concatenate(chunk_audio))
            done += len(chunk_bits)
            pct = int((done / total_bits) * 100)
            if pct != last_pct and pct % 10 == 0:
                cprint(f"  {pct}% done ({done}/{total_bits} bits)...", C.DIM, delay=0)
                last_pct = pct

def save_mp3(wav_filepath, mp3_filepath):
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_filepath, mp3_filepath], capture_output=True)
        if result.returncode == 0:
            cprint(f"  MP3 saved: {mp3_filepath}", C.GREEN)
            log("Saved MP3", mp3_filepath)
        else:
            cprint("  MP3 skipped: ffmpeg not found. WAV saved successfully.", C.YELLOW)
            cprint("  (Install ffmpeg from https://ffmpeg.org/download.html)", C.DIM)
    except FileNotFoundError:
        cprint("  MP3 skipped: ffmpeg not found. WAV saved successfully.", C.YELLOW)

def save_audio_files(binary, filename_base):
    wav_fp = audio_path(filename_base + ".wav")
    mp3_fp = audio_path(filename_base + ".mp3")
    cprint("  Writing audio in chunks (please wait)...", C.DIM)
    save_wav_chunked(binary, wav_fp)
    cprint(f"  WAV saved: {wav_fp}", C.GREEN)
    log("Saved WAV", f"{len(binary)} bits | path={wav_fp}")
    save_mp3(wav_fp, mp3_fp)

def save_binary_txt(binary, filename_base, header_line=None):
    fp     = txt_path(filename_base + ".txt")
    groups = [binary[i:i+8] for i in range(0, len(binary), 8)]
    with open(fp, "w", encoding="utf-8") as f:
        if header_line:
            f.write(header_line + "\n")
        f.write("\n".join(groups))
    cprint(f"  TXT saved: {fp}", C.GREEN)
    log("Saved binary TXT", f"{len(binary)} bits | path={fp}")
    return fp

def output_binary(binary_result):
    time.sleep(0.1)
    if len(binary_result) > 200:
        cprint(f"\n  {len(binary_result)} bits decoded -- too many to display.", C.CYAN)
        filename = input(f"  {C.YELLOW}Filename for TXT (without extension){C.RESET}: ").strip() or "decoded"
        save_binary_txt(binary_result, filename)
        cprint(f"\n  Done! Saved to TextFiles folder.", C.GREEN + C.BOLD)
    else:
        cprint(f"\n  Decoded binary: {binary_result}", C.GREEN + C.BOLD)

def validate_binary_input(raw):
    binary  = raw.replace(" ", "").replace("\n", "").replace("\r", "")
    invalid = set(binary) - {"0", "1"}
    if invalid:
        cprint(f"  Error: Invalid characters: {' '.join(sorted(invalid))}", C.RED)
        return None
    if not binary:
        cprint("  Error: No binary data found.", C.RED)
        return None
    return binary

def decode_wav_file(filepath, decode_rows=None):
    try:
        audio_data, sample_rate = sf.read(filepath, dtype='float32')
        if audio_data.ndim > 1:
            audio_data = audio_data[:, 0]
    except Exception as e:
        cprint(f"  Error reading file: {e}", C.RED)
        return None

    cprint("  Analyzing file...", C.DIM)
    time.sleep(0.1)

    chunk_size    = int(SETTINGS["tone_duration"] * sample_rate)
    num_chunks    = len(audio_data) // chunk_size
    binary_result = ""

    for i in range(num_chunks):
        chunk = audio_data[i * chunk_size:(i + 1) * chunk_size]
        if decode_rows:
            row = (i // 8) % 3
            fz  = decode_rows[row]["freq_zero"]
            fo  = decode_rows[row]["freq_one"]
        else:
            fz, fo = get_row_freqs(i)
        bit = detect_bit(chunk, sample_rate, fz, fo)
        if bit is None:
            cprint(f"\n  Could not decode -- frequencies don't match at bit {i}.", C.RED)
            cprint(f"  Expected: 0={fz} Hz, 1={fo} Hz", C.YELLOW)
            return None
        binary_result += bit
    return binary_result

def ask_row_freqs():
    cprint("\n  Row mode active. Enter the 3 row frequencies to decode.\n", C.YELLOW)
    rows = []
    for i in range(3):
        cprint(f"  -- ROW {i+1} --", C.YELLOW + C.BOLD)
        fz = ask_float(f"  Row {i+1} freq for 0", SETTINGS["rows"][i]["freq_zero"], 100, 5000)
        fo = ask_float(f"  Row {i+1} freq for 1", SETTINGS["rows"][i]["freq_one"],  100, 5000)
        rows.append({"freq_zero": fz, "freq_one": fo})
    for i in range(3):
        if (rows[i]["freq_zero"] != SETTINGS["rows"][i]["freq_zero"] or
            rows[i]["freq_one"]  != SETTINGS["rows"][i]["freq_one"]):
            cprint("\n  Row frequencies do not match session key. Cannot decode.", C.RED)
            return None
    return rows

def _read_any_file_as_binary(filepath):
    try:
        with open(filepath, "rb") as f:
            data = f.read()
        return "".join(format(b, "08b") for b in data), len(data)
    except Exception as e:
        cprint(f"  Error reading file: {e}", C.RED)
        return None, 0

# -- HEADER BLOCK --------------------------------------------------------------
# The header is a 200-character text message encoded at FIXED frequencies
# (header_freq_zero / header_freq_one from settings.txt), prepended to a WAV.

HEADER_CHARS = 200  # fixed size in characters
HEADER_SEPARATOR = "|||HEADER_END|||"  # written as binary after the text

def text_to_binary(text):
    return "".join(format(ord(c), "08b") for c in text)

def binary_to_text(binary):
    chars = []
    for i in range(0, len(binary) - 7, 8):
        try:
            chars.append(chr(int(binary[i:i+8], 2)))
        except Exception:
            chars.append("?")
    return "".join(chars)

def encode_header_block(message):
    """Encode a padded 200-char message + separator as WAV audio using header freqs."""
    padded    = message[:HEADER_CHARS].ljust(HEADER_CHARS)
    full_text = padded + HEADER_SEPARATOR
    binary    = text_to_binary(full_text)
    audio     = []
    dur       = SETTINGS["header_tone_duration"]
    fz        = SETTINGS["header_freq_zero"]
    fo        = SETTINGS["header_freq_one"]
    vol       = SETTINGS["volume"]
    samples   = int(dur * SAMPLE_RATE)

    for bit in binary:
        freq = fo if bit == "1" else fz
        t    = np.linspace(0, dur, samples, endpoint=False)
        audio.append(vol * np.sin(2 * np.pi * freq * t).astype(np.float32))
    return np.concatenate(audio)

def decode_header_from_wav(filepath):
    """Try to decode the header block from the start of a WAV file."""
    try:
        audio_data, sample_rate = sf.read(filepath, dtype='float32')
        if audio_data.ndim > 1:
            audio_data = audio_data[:, 0]
    except Exception as e:
        cprint(f"  Error reading file: {e}", C.RED)
        return None

    fz       = SETTINGS["header_freq_zero"]
    fo       = SETTINGS["header_freq_one"]
    dur      = SETTINGS["header_tone_duration"]
    tolerance = max(80, int(1.0 / dur) * 2)

    # We expect (200 chars + separator) * 8 bits each
    sep_bits      = len(text_to_binary(HEADER_SEPARATOR))
    total_bits    = (HEADER_CHARS + len(HEADER_SEPARATOR)) * 8
    chunk_size    = int(dur * sample_rate)

    if len(audio_data) < chunk_size * total_bits:
        return None

    binary = ""
    for i in range(total_bits):
        chunk    = audio_data[i * chunk_size:(i + 1) * chunk_size]
        bit      = detect_bit(chunk, sample_rate, fz, fo, tolerance)
        binary  += bit if bit else "0"

    text = binary_to_text(binary)
    if HEADER_SEPARATOR not in text:
        return None
    return text.split(HEADER_SEPARATOR)[0].rstrip()

# -- INFILES BROWSER -----------------------------------------------------------

def browse_infiles():
    """Show files in the Infiles folder and let the user pick one."""
    try:
        all_files = [f for f in os.listdir(INFILES_DIR)
                     if os.path.isfile(os.path.join(INFILES_DIR, f))]
    except Exception as e:
        cprint(f"  Error reading Infiles folder: {e}", C.RED)
        return

    if not all_files:
        cprint(f"\n  Infiles folder is empty.", C.YELLOW)
        cprint(f"  Drop files into: {INFILES_DIR}", C.DIM)
        return

    all_files.sort()
    while True:
        time.sleep(0.1)
        divider()
        cprint(f"    INFILES  ({INFILES_DIR})", C.CYAN + C.BOLD)
        divider()
        for i, fname in enumerate(all_files, 1):
            size = os.path.getsize(os.path.join(INFILES_DIR, fname))
            size_str = f"{size:,} bytes" if size < 1024 else f"{size//1024:,} KB"
            cprint(f"  {C.CYAN}{i:2}{C.RESET} - {fname}  {C.DIM}({size_str}){C.RESET}", delay=0.02)
        cprint(f"  {C.CYAN} 0{C.RESET} - Back", delay=0.02)

        choice = input(f"\n  {C.YELLOW}Pick a file number{C.RESET}: ").strip()
        if choice == "0":
            return
        elif _check_scram(choice):
            pass
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(all_files):
                    filepath = os.path.join(INFILES_DIR, all_files[idx])
                    logaction(f"Infiles: selected '{all_files[idx]}' | path={filepath}")
                    _infile_actions(filepath, all_files[idx])
                else:
                    cprint(f"  Please enter 0-{len(all_files)}.", C.RED)
            except ValueError:
                cprint("  Please enter a number.", C.RED)

def _infile_actions(filepath, fname):
    """Show what the user can do with the chosen infile."""
    ext    = os.path.splitext(fname)[1].lower()
    is_wav = ext == ".wav"
    is_txt = ext == ".txt"

    while True:
        time.sleep(0.1)
        divider()
        cprint(f"    {fname}", C.CYAN + C.BOLD)
        divider()
        cprint(f"  {C.CYAN}1{C.RESET} - Convert to binary TXT",             delay=0.03)
        cprint(f"  {C.CYAN}2{C.RESET} - Convert to WAV + MP3",              delay=0.03)
        cprint(f"  {C.CYAN}3{C.RESET} - Convert to WAV + MP3 with header",  delay=0.03)
        if is_wav:
            cprint(f"  {C.CYAN}4{C.RESET} - Decode WAV -> binary / TXT",    delay=0.03)
            cprint(f"  {C.CYAN}5{C.RESET} - Read header only",              delay=0.03)
        elif is_txt:
            cprint(f"  {C.CYAN}4{C.RESET} - Use as binary input -> WAV + MP3", delay=0.03)
        cprint(f"  {C.CYAN}0{C.RESET} - Back to file list", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            binary, byte_count = _read_any_file_as_binary(filepath)
            if binary is None:
                continue
            cprint(f"  {byte_count} bytes = {len(binary)} bits.", C.CYAN)
            outname = input(f"  {C.YELLOW}Output filename (no extension){C.RESET}: ").strip() or "infile_binary"
            save_binary_txt(binary, outname, header_line=f"ORIGINAL_FILENAME:{fname}")
            cprint("  Saved to TextFiles folder.", C.GREEN + C.BOLD)

        elif choice == "2":
            binary, byte_count = _read_any_file_as_binary(filepath)
            if binary is None:
                continue
            cprint(f"  {byte_count} bytes = {len(binary)} bits.", C.CYAN)
            outname = input(f"  {C.YELLOW}Output filename (no extension){C.RESET}: ").strip() or "infile_audio"
            save_audio_files(binary, outname)
            cprint("  Saved to Audio folder.", C.GREEN + C.BOLD)

        elif choice == "3":
            # Convert to WAV with a header block prepended
            binary, byte_count = _read_any_file_as_binary(filepath)
            if binary is None:
                continue
            cprint(f"  {byte_count} bytes = {len(binary)} bits.", C.CYAN)
            cprint(f"\n  Header block uses fixed frequencies:", C.CYAN)
            cprint(f"    0={SETTINGS['header_freq_zero']} Hz, "
                   f"1={SETTINGS['header_freq_one']} Hz, "
                   f"{SETTINGS['header_tone_duration']}s/bit  [from settings.txt]", C.DIM)
            cprint(f"  Max {HEADER_CHARS} characters.\n", C.DIM)
            message = input(f"  {C.YELLOW}Header message (max {HEADER_CHARS} chars){C.RESET}: ")
            if len(message) > HEADER_CHARS:
                cprint(f"  Truncated to {HEADER_CHARS} characters.", C.YELLOW)
                message = message[:HEADER_CHARS]
            outname = input(f"  {C.YELLOW}Output filename (no extension){C.RESET}: ").strip() or "infile_header"
            wav_fp  = audio_path(outname + ".wav")
            mp3_fp  = audio_path(outname + ".mp3")

            cprint("\n  Encoding header block...", C.DIM)
            header_audio = encode_header_block(message)

            cprint("  Encoding payload (chunked)...", C.DIM)
            tmp_path = audio_path("_tmp_payload.wav")
            save_wav_chunked(binary, tmp_path)

            try:
                payload_data, _ = sf.read(tmp_path, dtype='float32')
                full_audio = np.concatenate([header_audio, payload_data])
                sf.write(wav_fp, full_audio, SAMPLE_RATE)
                os.remove(tmp_path)
                cprint(f"  WAV saved: {wav_fp}", C.GREEN)
                save_mp3(wav_fp, mp3_fp)
                cprint("  Done! Saved to Audio folder.", C.GREEN + C.BOLD)
            except Exception as e:
                cprint(f"  Error merging audio: {e}", C.RED)

        elif choice == "4" and is_wav:
            decode_rows = ask_row_freqs() if SETTINGS["row_mode"] else None
            if SETTINGS["row_mode"] and decode_rows is None:
                continue
            result = decode_wav_file(filepath, decode_rows)
            if result:
                output_binary(result)

        elif choice == "5" and is_wav:
            cprint("\n  Reading header block...", C.DIM)
            header = decode_header_from_wav(filepath)
            if header:
                cprint(f"\n  Header text:", C.CYAN + C.BOLD)
                cprint(f"  {header}", C.WHITE)
            else:
                cprint("  No header block found in this WAV file.", C.YELLOW)
                cprint("  The file may not have a header, or header frequencies", C.DIM)
                cprint("  in settings.txt may have changed since encoding.", C.DIM)

        elif choice == "4" and is_txt:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception as e:
                cprint(f"  Error: {e}", C.RED)
                continue
            if lines and lines[0].startswith("ORIGINAL_FILENAME:"):
                lines = lines[1:]
            binary = validate_binary_input("".join(lines))
            if not binary:
                continue
            cprint(f"\n  {len(binary)} bits found.", C.CYAN)
            outname = input(f"  {C.YELLOW}Output filename (no extension){C.RESET}: ").strip() or "infile_output"
            save_audio_files(binary, outname)
            cprint("  Saved to Audio folder.", C.GREEN + C.BOLD)

        else:
            cprint("  Invalid choice.", C.RED)

# -- STARTUP CONFIG ------------------------------------------------------------

def configure_settings():
    time.sleep(0.1)
    cprint("\n" + "=" * 45, C.CYAN)
    cprint("         STARTUP CONFIGURATION", C.CYAN + C.BOLD)
    cprint("=" * 45, C.CYAN)

    locked = []
    if SETTINGS["lock_freq_zero"]:     locked.append("freq_zero")
    if SETTINGS["lock_freq_one"]:      locked.append("freq_one")
    if SETTINGS["lock_tone_duration"]: locked.append("tone_duration")
    if SETTINGS["lock_volume"]:        locked.append("volume")

    if locked:
        cprint(f"  Locked by settings.txt: {', '.join(locked)}", C.YELLOW, delay=0.05)

    cprint("  Press Enter to keep the default value.\n", C.DIM, delay=0.05)

    if not SETTINGS["lock_freq_zero"]:
        SETTINGS["freq_zero"] = ask_float(
            "Frequency for 0 in Hz  (e.g. 440)", SETTINGS["freq_zero"], 100, 5000)
    else:
        cprint(f"  Frequency for 0 : {SETTINGS['freq_zero']} Hz  [locked]", C.DIM)

    if not SETTINGS["lock_freq_one"]:
        SETTINGS["freq_one"] = ask_float(
            "Frequency for 1 in Hz  (e.g. 880)", SETTINGS["freq_one"], 100, 5000)
    else:
        cprint(f"  Frequency for 1 : {SETTINGS['freq_one']} Hz  [locked]", C.DIM)

    if not SETTINGS["lock_tone_duration"]:
        SETTINGS["tone_duration"] = ask_float(
            "Tone duration in sec   (e.g. 0.01)", SETTINGS["tone_duration"], 0.005, 2.0)
    else:
        cprint(f"  Tone duration   : {SETTINGS['tone_duration']}s  [locked]", C.DIM)

    if not SETTINGS["lock_volume"]:
        SETTINGS["volume"] = ask_float(
            "Volume 0.0-1.0         (e.g. 0.5)", SETTINGS["volume"], 0.0, 1.0)
    else:
        cprint(f"  Volume          : {SETTINGS['volume']}  [locked]", C.DIM)

    if SETTINGS["freq_zero"] == SETTINGS["freq_one"]:
        cprint("\n  Warning: Frequencies for 0 and 1 are the same!", C.RED)

    time.sleep(0.1)
    cprint("\n  Settings active:", C.DIM)
    cprint(f"    0 tone : {SETTINGS['freq_zero']} Hz", C.BLUE)
    cprint(f"    1 tone : {SETTINGS['freq_one']} Hz", C.GREEN)
    cprint(f"    Speed  : {SETTINGS['tone_duration']}s/bit ({1/SETTINGS['tone_duration']:.1f} bits/sec)", C.CYAN)
    cprint(f"    Volume : {SETTINGS['volume']}", C.CYAN)
    cprint(f"    Header : 0={SETTINGS['header_freq_zero']} Hz / 1={SETTINGS['header_freq_one']} Hz / {SETTINGS['header_tone_duration']}s  [locked in settings.txt]", C.DIM)
    logaction(f"Audio settings set: 0={SETTINGS['freq_zero']}Hz 1={SETTINGS['freq_one']}Hz dur={SETTINGS['tone_duration']}s vol={SETTINGS['volume']}")

def configure_row_mode():
    SETTINGS["row_mode"] = True
    cprint("\n" + "=" * 45, C.YELLOW)
    cprint("          ROW MODE -- 3 ROW SYSTEM", C.YELLOW + C.BOLD)
    cprint("=" * 45, C.YELLOW)
    cprint("  Every 8 bits uses a different row.", C.DIM)
    for label in ["Bits  1-8  -> Row 1", "Bits  9-16 -> Row 2",
                  "Bits 17-24 -> Row 3", "Bits 25-32 -> Row 1  (repeats)"]:
        cprint(f"  {label}", C.DIM)
    print()

    for i in range(3):
        cprint(f"  -- ROW {i+1} --", C.YELLOW + C.BOLD)
        fz = ask_float(f"  Row {i+1} freq for 0",
                       SETTINGS["rows"][i]["freq_zero"], 100, 5000)
        fo = ask_float(f"  Row {i+1} freq for 1",
                       SETTINGS["rows"][i]["freq_one"],  100, 5000)
        if fz == fo:
            cprint(f"  Warning: Row {i+1} frequencies are the same!", C.RED)
        SETTINGS["rows"][i] = {"freq_zero": fz, "freq_one": fo}
        cprint(f"  Row {i+1}: 0={fz} Hz, 1={fo} Hz", C.GREEN)

    # Save key file
    key_fp = keys_path("row_key.txt")
    with open(key_fp, "w", encoding="utf-8") as f:
        f.write("BINARY SOUND CONVERTER -- ROW KEY FILE\n")
        f.write("=" * 40 + "\n")
        for i, row in enumerate(SETTINGS["rows"]):
            f.write(f"Row {i+1}: 0={row['freq_zero']} Hz, 1={row['freq_one']} Hz\n")
        f.write("=" * 40 + "\n")
        f.write(f"Tone duration: {SETTINGS['tone_duration']} seconds\n")

    # Save row settings back to settings.txt
    _update_settings_file("row_mode", "true")
    for i, row in enumerate(SETTINGS["rows"]):
        _update_settings_file(f"row{i+1}_freq_zero", row["freq_zero"])
        _update_settings_file(f"row{i+1}_freq_one",  row["freq_one"])

    cprint(f"\n  Key file saved: {key_fp}", C.GREEN + C.BOLD)
    log("Row key file saved", key_fp)
    cprint("  Row settings saved to settings.txt.", C.GREEN)
    log("Row mode enabled", f"Rows: {SETTINGS['rows']}")

# ==============================================================================
#  MENU 1 -- BINARY TO SOUND
# ==============================================================================

def menu_binary_to_sound():
    while True:
        time.sleep(0.1)
        divider()
        cprint("    BINARY -> SOUND", C.CYAN + C.BOLD)
        divider()
        cprint(f"  {C.CYAN}1{C.RESET} - Type binary -> Play sound",           delay=0.03)
        cprint(f"  {C.CYAN}2{C.RESET} - Type binary -> Save WAV + MP3",        delay=0.03)
        cprint(f"  {C.CYAN}3{C.RESET} - TXT file -> Save WAV + MP3",           delay=0.03)
        cprint(f"  {C.CYAN}4{C.RESET} - Flip binary",                         delay=0.03)
        cprint(f"  {C.CYAN}5{C.RESET} - Save WAV with header block",           delay=0.03)
        cprint(f"  {C.CYAN}0{C.RESET} - Back", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip()
        if choice == "0":   break
        elif _check_scram(choice): pass
        elif choice == "1": logaction("Binary->Sound: Play sound"); _b2s_play()
        elif choice == "2": logaction("Binary->Sound: Save WAV+MP3"); _b2s_save()
        elif choice == "3": logaction("Binary->Sound: TXT file to WAV"); _b2s_txt_to_wav()
        elif choice == "4": logaction("Binary->Sound: Flip binary"); _b2s_flip()
        elif choice == "5": logaction("Binary->Sound: Save with header"); _b2s_with_header()
        else: cprint("  Please enter 0-5.", C.RED)

def _b2s_play():
    binary = validate_binary_input(
        input(f"\n  {C.YELLOW}Enter binary{C.RESET}: "))
    if not binary: return
    cprint(f"\n  Playing {len(binary)} bits...", C.CYAN)
    print("  ", end="")
    audio = []
    for i, bit in enumerate(binary):
        fz, fo = get_row_freqs(i)
        audio.append(make_tone(fo if bit == "1" else fz, SETTINGS["tone_duration"]))
        print((C.BLUE if bit == "0" else C.GREEN) + bit + C.RESET, end=" ", flush=True)
    print("\n")
    sd.play(np.concatenate(audio), SAMPLE_RATE)
    sd.wait()
    cprint("  Done!", C.GREEN)
    logaction(f"Played {len(binary)} bits as sound")

def _b2s_save():
    binary = validate_binary_input(input(f"\n  {C.YELLOW}Enter binary{C.RESET}: "))
    if not binary: return
    fn = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or "output"
    save_audio_files(binary, fn)
    cprint("  Saved to Audio folder.", C.GREEN + C.BOLD)

def _b2s_txt_to_wav():
    fp = input(f"\n  {C.YELLOW}Path to TXT file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint(f"  Error: File not found.", C.RED); return
    if not fp.lower().endswith(".txt"):
        cprint("  Error: Only .txt files.", C.RED); return
    logaction(f"TXT to WAV | input={fp}")
    try:
        with open(fp, "r", encoding="utf-8") as f: lines = f.readlines()
    except Exception as e:
        cprint(f"  Error: {e}", C.RED); return
    if lines and lines[0].startswith("ORIGINAL_FILENAME:"):
        lines = lines[1:]
    binary = validate_binary_input("".join(lines))
    if not binary: return
    cprint(f"\n  {len(binary)} bits found.", C.CYAN)
    fn = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or "output"
    save_audio_files(binary, fn)
    cprint("  Saved to Audio folder.", C.GREEN + C.BOLD)

def _b2s_flip():
    binary = validate_binary_input(input(f"\n  {C.YELLOW}Enter binary to flip{C.RESET}: "))
    if not binary: return
    flipped = "".join("1" if b == "0" else "0" for b in binary)
    cprint(f"\n  Original: {binary}", C.BLUE)
    cprint(f"  Flipped:  {flipped}", C.GREEN)
    action = input(f"\n  {C.CYAN}1{C.RESET} Play  {C.CYAN}2{C.RESET} Save  {C.CYAN}3{C.RESET} Nothing: ").strip()
    if action == "1":
        audio = [make_tone(get_row_freqs(i)[1] if b == "1" else get_row_freqs(i)[0],
                           SETTINGS["tone_duration"]) for i, b in enumerate(flipped)]
        sd.play(np.concatenate(audio), SAMPLE_RATE); sd.wait()
        cprint("  Done!", C.GREEN)
    elif action == "2":
        fn = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or "flipped"
        save_audio_files(flipped, fn)
    else:
        cprint("  Nothing saved.", C.DIM)

def _b2s_with_header():
    """Encode a header message + binary payload into one WAV file."""
    cprint(f"\n  Header block uses fixed frequencies:", C.CYAN)
    cprint(f"    0={SETTINGS['header_freq_zero']} Hz, 1={SETTINGS['header_freq_one']} Hz, "
           f"{SETTINGS['header_tone_duration']}s/bit  [from settings.txt]", C.DIM)
    cprint(f"  Max {HEADER_CHARS} characters.\n", C.DIM)

    message = input(f"  {C.YELLOW}Header message (max {HEADER_CHARS} chars){C.RESET}: ")
    if len(message) > HEADER_CHARS:
        cprint(f"  Truncated to {HEADER_CHARS} characters.", C.YELLOW)
        message = message[:HEADER_CHARS]

    cprint(f"\n  Now enter the binary payload:", C.CYAN)
    cprint(f"  Type binary directly, enter a file path, or leave blank for header-only.", C.DIM)
    raw_payload = input(f"  {C.YELLOW}Binary / file path (or blank){C.RESET}: ").strip()

    fn = input(f"  {C.YELLOW}Filename (no extension){C.RESET}: ").strip() or "header_output"
    wav_fp = audio_path(fn + ".wav")
    mp3_fp = audio_path(fn + ".mp3")

    cprint("\n  Encoding header block...", C.DIM)
    header_audio = encode_header_block(message)

    if raw_payload:
        # Check if it looks like a file path
        cleaned = raw_payload.strip('"')
        if os.path.exists(cleaned):
            cprint(f"  File detected -- reading as binary...", C.DIM)
            payload, byte_count = _read_any_file_as_binary(cleaned)
            if payload is None:
                return
            cprint(f"  {byte_count} bytes = {len(payload)} bits.", C.CYAN)
        else:
            payload = validate_binary_input(raw_payload)
            if not payload:
                return

        cprint("  Encoding payload (chunked)...", C.DIM)
        # Write header + payload together using chunked writer to handle large files
        tmp_payload_path = audio_path("_tmp_payload.wav")
        save_wav_chunked(payload, tmp_payload_path)

        # Merge header audio + payload WAV into final file
        try:
            payload_data, sr = sf.read(tmp_payload_path, dtype='float32')
            full_audio = np.concatenate([header_audio, payload_data])
            sf.write(wav_fp, full_audio, SAMPLE_RATE)
            os.remove(tmp_payload_path)
        except Exception as e:
            cprint(f"  Error merging audio: {e}", C.RED)
            return
    else:
        sf.write(wav_fp, header_audio, SAMPLE_RATE)
    cprint(f"  WAV saved: {wav_fp}", C.GREEN)
    log("Saved WAV with header", f"path={wav_fp}")
    save_mp3(wav_fp, mp3_fp)
    cprint("\n  Done! WAV with header saved to Audio folder.", C.GREEN + C.BOLD)

# ==============================================================================
#  MENU 2 -- SOUND TO BINARY
# ==============================================================================

def menu_sound_to_binary():
    while True:
        time.sleep(0.1)
        divider()
        cprint("    SOUND -> BINARY", C.CYAN + C.BOLD)
        divider()
        cprint(f"  {C.CYAN}1{C.RESET} - Record microphone -> Binary / TXT", delay=0.03)
        cprint(f"  {C.CYAN}2{C.RESET} - Load WAV file -> Binary / TXT",      delay=0.03)
        cprint(f"  {C.CYAN}3{C.RESET} - Read header only from WAV",          delay=0.03)
        cprint(f"  {C.CYAN}0{C.RESET} - Back", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip()
        if choice == "0":   break
        elif _check_scram(choice): pass
        elif choice == "1": logaction("Sound->Binary: Record microphone"); _s2b_record()
        elif choice == "2": logaction("Sound->Binary: Load WAV file"); _s2b_wav_file()
        elif choice == "3": logaction("Sound->Binary: Read header only"); _s2b_header_only()
        else: cprint("  Please enter 0-3.", C.RED)

def _s2b_record():
    try:
        device_info = sd.query_devices(kind='input')
        cprint(f"  Microphone: {device_info['name']}", C.DIM)
    except Exception:
        cprint("  Error: No microphone found.", C.RED); return

    try:
        dur = float(input(f"\n  {C.YELLOW}How many seconds to record?{C.RESET} "))
    except ValueError:
        cprint("  Please enter a number.", C.RED); return
    if dur <= 0:
        cprint("  Please enter a positive number.", C.RED); return

    cprint(f"\n  Make sure your speakers are playing the tones!", C.YELLOW)
    for i in range(3, 0, -1):
        cprint(f"  {i}...", C.YELLOW, delay=0.9)
    cprint("  GO!\n", C.GREEN + C.BOLD)

    try:
        rec = sd.rec(int(dur * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                     channels=1, dtype=np.float32)
        sd.wait()
    except Exception as e:
        cprint(f"  Error during recording: {e}", C.RED); return

    cprint("  Done! Analyzing...", C.DIM)
    audio  = rec.flatten()

    if np.max(np.abs(audio)) < 0.001:
        cprint("  Error: Recording was silent. Check microphone permissions.", C.RED)
        return

    chunk_size    = int(SETTINGS["tone_duration"] * SAMPLE_RATE)
    num_chunks    = len(audio) // chunk_size
    if num_chunks == 0:
        cprint("  Error: Recording too short.", C.RED); return

    binary_result = ""
    failed        = 0
    for i in range(num_chunks):
        chunk  = audio[i * chunk_size:(i + 1) * chunk_size]
        fz, fo = get_row_freqs(i)
        bit    = detect_bit(chunk, SAMPLE_RATE, fz, fo)
        if bit is None:
            failed += 1; binary_result += "?"
        else:
            binary_result += bit

    if failed == num_chunks:
        cprint("\n  Could not decode anything.", C.RED)
        cprint(f"  Expected: 0={SETTINGS['freq_zero']} Hz, 1={SETTINGS['freq_one']} Hz", C.YELLOW)
        cprint("  Try: longer tone duration, speakers near mic, quiet room.", C.DIM)
        logaction("Microphone decode: FAILED -- no matching frequencies")
        return
    elif failed / num_chunks > 0.2:
        cprint(f"\n  Warning: {failed}/{num_chunks} bits unclear. Shown as '?'", C.YELLOW)
        logaction(f"Microphone decode: partial -- {failed}/{num_chunks} bits unclear")

    output_binary(binary_result)

def _s2b_wav_file():
    decode_rows = ask_row_freqs() if SETTINGS["row_mode"] else None
    if SETTINGS["row_mode"] and decode_rows is None: return
    fp = input(f"\n  {C.YELLOW}Path to WAV file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED); return
    logaction(f"Decode WAV | path={fp}")
    result = decode_wav_file(fp, decode_rows)
    if result is not None:
        output_binary(result)

def _s2b_header_only():
    fp = input(f"\n  {C.YELLOW}Path to WAV file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED); return
    logaction(f"Read header | path={fp}")
    cprint("\n  Reading header block...", C.DIM)
    header = decode_header_from_wav(fp)
    if header:
        cprint(f"\n  Header text:", C.CYAN + C.BOLD)
        cprint(f"  {header}", C.WHITE)
    else:
        cprint("  No header block found.", C.YELLOW)
        cprint("  The file may have no header, or header frequencies changed.", C.DIM)

# ==============================================================================
#  MENU 3 -- FILE TOOLS
# ==============================================================================

def menu_file_tools():
    while True:
        time.sleep(0.1)
        divider()
        cprint("    FILE TOOLS", C.CYAN + C.BOLD)
        divider()
        cprint(f"  {C.CYAN}1{C.RESET} - Any file -> Binary TXT",     delay=0.03)
        cprint(f"  {C.CYAN}2{C.RESET} - Any file -> WAV + MP3",      delay=0.03)
        cprint(f"  {C.CYAN}3{C.RESET} - Binary TXT -> Rebuild file", delay=0.03)
        cprint(f"  {C.CYAN}0{C.RESET} - Back", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip().lower()
        if choice == "0":        break
        elif _check_scram(choice): pass
        elif choice == "1":      logaction("File Tools: File to binary TXT"); _ft_file_to_txt()
        elif choice == "2":      logaction("File Tools: File to WAV+MP3"); _ft_file_to_wav()
        elif choice == "3":      logaction("File Tools: Rebuild file from TXT"); _ft_txt_to_file()
        elif choice == "infiles": logaction("File Tools: Opened Infiles browser"); browse_infiles()
        else: cprint("  Please enter 0-3.", C.RED)

def _ft_file_to_txt():
    fp = input(f"\n  {C.YELLOW}Path to any file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED); return
    logaction(f"File to binary TXT | input={fp}")
    binary, n = _read_any_file_as_binary(fp)
    if binary is None: return
    cprint(f"  {n} bytes = {len(binary)} bits.", C.CYAN)
    fn = input(f"  {C.YELLOW}Output filename (no extension){C.RESET}: ").strip() or "file_binary"
    save_binary_txt(binary, fn, header_line=f"ORIGINAL_FILENAME:{os.path.basename(fp)}")
    cprint("  Saved to TextFiles folder.", C.GREEN + C.BOLD)

def _ft_file_to_wav():
    fp = input(f"\n  {C.YELLOW}Path to any file{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED); return
    logaction(f"File to WAV | input={fp}")
    binary, n = _read_any_file_as_binary(fp)
    if binary is None: return
    cprint(f"  {n} bytes = {len(binary)} bits.", C.CYAN)
    fn = input(f"  {C.YELLOW}Output filename (no extension){C.RESET}: ").strip() or "file_audio"
    save_audio_files(binary, fn)
    cprint("  Saved to Audio folder.", C.GREEN + C.BOLD)

def _ft_txt_to_file():
    fp = input(f"\n  {C.YELLOW}Path to binary TXT{C.RESET}: ").strip().strip('"')
    if not os.path.exists(fp):
        cprint("  Error: File not found.", C.RED); return
    if not fp.lower().endswith(".txt"):
        cprint("  Error: Only .txt files.", C.RED); return
    logaction(f"Rebuild file from TXT | input={fp}")
    try:
        with open(fp, "r", encoding="utf-8") as f: lines = f.readlines()
    except Exception as e:
        cprint(f"  Error: {e}", C.RED); return

    original_name = None
    # Strip any known header lines from the top
    while lines and (
        lines[0].startswith("ORIGINAL_FILENAME:") or
        lines[0].startswith("#") or
        lines[0].strip() == ""
    ):
        if lines[0].startswith("ORIGINAL_FILENAME:"):
            original_name = lines[0].strip().replace("ORIGINAL_FILENAME:", "")
        lines = lines[1:]

    binary = validate_binary_input("".join(lines))
    if binary is None: return
    if len(binary) % 8 != 0:
        binary = binary.ljust((len(binary) + 7) // 8 * 8, "0")

    byte_array = bytearray(int(binary[i:i+8], 2) for i in range(0, len(binary), 8))

    if original_name:
        cprint(f"  Original filename: {original_name}", C.CYAN)
        use_orig = input(f"  {C.YELLOW}Use original filename? (y/n){C.RESET}: ").strip().lower()
        out_fn   = original_name if use_orig == "y" else (
            input(f"  {C.YELLOW}Filename (with extension){C.RESET}: ").strip() or "rebuilt.bin")
    else:
        out_fn = input(f"  {C.YELLOW}Filename (with extension){C.RESET}: ").strip() or "rebuilt.bin"

    out_fp = files_path(out_fn)
    try:
        with open(out_fp, "wb") as f: f.write(byte_array)
        cprint(f"  Saved: {out_fp}", C.GREEN)
        cprint(f"  {len(byte_array)} bytes rebuilt.", C.GREEN + C.BOLD)
        log("Rebuilt file", f"{len(byte_array)} bytes -> {out_fp}")
    except Exception as e:
        cprint(f"  Error: {e}", C.RED)

# ==============================================================================
#  MENU 4 -- SETTINGS
# ==============================================================================

def menu_settings():
    while True:
        time.sleep(0.1)
        divider()
        cprint("    SETTINGS", C.CYAN + C.BOLD)
        divider()
        cprint(f"  {C.CYAN}1{C.RESET} - Show current settings",  delay=0.03)
        cprint(f"  {C.CYAN}2{C.RESET} - Change audio settings",  delay=0.03)
        cprint(f"  {C.CYAN}3{C.RESET} - Change output folder",   delay=0.03)
        cprint(f"  {C.CYAN}4{C.RESET} - Open settings.txt",      delay=0.03)
        cprint(f"  {C.CYAN}5{C.RESET} - Row Mode",               delay=0.03)
        cprint(f"  {C.CYAN}6{C.RESET} - View log",               delay=0.03)
        cprint(f"  {C.CYAN}7{C.RESET} - Change log file path",   delay=0.03)
        cprint(f"  {C.CYAN}0{C.RESET} - Back", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip()
        if choice == "0":   break
        elif _check_scram(choice): pass
        elif choice == "1": logaction("Settings: Viewed settings"); _show_settings()
        elif choice == "2": logaction("Settings: Changed audio settings"); configure_settings()
        elif choice == "3": logaction("Settings: Changed output folder"); _change_output_folder()
        elif choice == "4": logaction("Settings: Opened settings.txt"); _open_settings_file()
        elif choice == "5": logaction("Settings: Opened Row Mode menu"); _row_mode_menu()
        elif choice == "6": logaction("Settings: Viewed log"); _view_log()
        elif choice == "7": logaction("Settings: Changed log file path"); _change_log_path()
        else: cprint("  Please enter 0-7.", C.RED)

def _row_mode_menu():
    while True:
        time.sleep(0.1)
        divider()
        row_status = C.GREEN + "ON" + C.RESET if SETTINGS["row_mode"] else C.RED + "OFF" + C.RESET
        cprint(f"    ROW MODE  [{row_status}]", C.CYAN + C.BOLD)
        divider()
        cprint(f"  {C.CYAN}1{C.RESET} - {'Disable' if SETTINGS['row_mode'] else 'Enable'} row mode", delay=0.03)
        cprint(f"  {C.CYAN}2{C.RESET} - Configure row frequencies", delay=0.03)
        cprint(f"  {C.CYAN}3{C.RESET} - Show current row frequencies", delay=0.03)
        cprint(f"  {C.CYAN}0{C.RESET} - Back", delay=0.03)

        choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip()
        if choice == "0":
            break
        elif _check_scram(choice): pass
        elif choice == "1":
            SETTINGS["row_mode"] = not SETTINGS["row_mode"]
            state = "enabled" if SETTINGS["row_mode"] else "disabled"
            _update_settings_file("row_mode", "true" if SETTINGS["row_mode"] else "false")
            cprint(f"  Row mode {state}.", C.GREEN)
            logaction(f"Row mode {state}")
            log(f"Row mode {state}")
        elif choice == "2":
            configure_row_mode()
        elif choice == "3":
            for i, row in enumerate(SETTINGS["rows"]):
                cprint(f"  Row {i+1}: 0={row['freq_zero']} Hz, 1={row['freq_one']} Hz", C.CYAN)
        else:
            cprint("  Please enter 0-3.", C.RED)

def _view_log():
    if not os.path.exists(LOG_FILE):
        cprint("\n  Log file is empty or does not exist yet.", C.YELLOW)
        cprint(f"  Expected at: {LOG_FILE}", C.DIM)
        return

    size = os.path.getsize(LOG_FILE)
    size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.2f} MB"

    cprint(f"\n  Log file: {LOG_FILE}", C.CYAN + C.BOLD)
    cprint(f"  Size: {size_str} / 10 MB max", C.DIM)

    action = input(f"\n  {C.CYAN}1{C.RESET} Show last 20 lines  {C.CYAN}2{C.RESET} Open in editor  {C.CYAN}3{C.RESET} Clear log  {C.CYAN}0{C.RESET} Back: ").strip()

    if action == "1":
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            last = lines[-20:] if len(lines) > 20 else lines
            cprint(f"\n  Last {len(last)} log entries:", C.CYAN)
            for line in last:
                cprint(f"  {line.rstrip()}", C.DIM, delay=0.01)
        except Exception as e:
            cprint(f"  Error reading log: {e}", C.RED)
    elif action == "2":
        _open_file_in_editor(LOG_FILE)
    elif action == "3":
        confirm = input(f"  {C.YELLOW}Are you sure you want to clear the log? (y/n){C.RESET}: ").strip().lower()
        if confirm == "y":
            try:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.write("")
                cprint("  Log cleared.", C.GREEN)
            except Exception as e:
                cprint(f"  Error: {e}", C.RED)
    cprint("\n  Session settings:", C.CYAN + C.BOLD)
    row_status2 = (C.GREEN + 'ON' + C.RESET) if SETTINGS['row_mode'] else (C.RED + 'OFF' + C.RESET)
    cprint(f'    Row Mode : {row_status2}', C.RESET)
    if SETTINGS["row_mode"]:
        for i, row in enumerate(SETTINGS["rows"]):
            cprint(f"    Row {i+1}  : 0={row['freq_zero']} Hz, 1={row['freq_one']} Hz", C.CYAN)
    else:
        lock0 = " [locked]" if SETTINGS["lock_freq_zero"] else ""
        lock1 = " [locked]" if SETTINGS["lock_freq_one"]  else ""
        lockd = " [locked]" if SETTINGS["lock_tone_duration"] else ""
        lockv = " [locked]" if SETTINGS["lock_volume"]    else ""
        cprint(f"    0 tone : {SETTINGS['freq_zero']} Hz{lock0}", C.BLUE)
        cprint(f"    1 tone : {SETTINGS['freq_one']} Hz{lock1}", C.GREEN)
        cprint(f"    Speed  : {SETTINGS['tone_duration']}s/bit{lockd}", C.CYAN)
        cprint(f"    Volume : {SETTINGS['volume']}{lockv}", C.CYAN)
    cprint(f"\n  Header block (locked in settings.txt):", C.DIM)
    cprint(f"    0={SETTINGS['header_freq_zero']} Hz / 1={SETTINGS['header_freq_one']} Hz / {SETTINGS['header_tone_duration']}s/bit", C.DIM)
    cprint(f"\n  Folders:", C.DIM)
    cprint(f"    Output   -> {BASE_DIR}", C.DIM)
    cprint(f"    Infiles  -> {INFILES_DIR}", C.DIM)
    cprint(f"    Audio    -> {AUDIO_DIR}", C.DIM)
    cprint(f"    TextFiles-> {TXT_DIR}", C.DIM)
    cprint(f"    Rebuilt  -> {FILES_DIR}", C.DIM)
    cprint(f"    Keys     -> {KEYS_DIR}", C.DIM)
    cprint(f"  Settings file: {SETTINGS_FILE}", C.DIM)
    time.sleep(0.1)
    cprint(f"\n  Special commands (work in all menus):", C.DIM)
    cprint(f"    infiles -- browse quick-access folder", C.DIM)
    cprint(f"    scram   -- emergency delete of all app data", C.DIM)
    cprint(f"              (folders, log, settings -- asks confirmation)", C.DIM)

def _change_log_path():
    cprint(f"\n  Current log file: {LOG_FILE}", C.CYAN + C.BOLD)
    cprint("  Enter a new full path including filename, or press Enter to keep current.", C.DIM)
    cprint("  Example: C:\\Users\\YourName\\Desktop\\bsc_log.txt", C.DIM, delay=0.1)
    new_path = input(f"\n  {C.YELLOW}New log file path{C.RESET}: ").strip().strip('"')
    if not new_path:
        cprint("  No change made.", C.DIM); return
    if not os.path.isabs(new_path):
        cprint("  Error: Please enter a full path.", C.RED); return
    if not new_path.lower().endswith(".txt"):
        cprint("  Error: Log file must end in .txt", C.RED); return
    set_log_file(new_path)
    _update_settings_file("log_file", new_path)
    cprint(f"\n  Log file path changed to: {LOG_FILE}", C.GREEN + C.BOLD)
    cprint("  Saved to settings.txt.", C.GREEN)
    log("Log path changed", LOG_FILE)

def _change_output_folder():
    cprint(f"\n  Current output folder: {BASE_DIR}", C.CYAN + C.BOLD)
    cprint("  Enter a new full path, or press Enter to keep current.", C.DIM)
    new_path = input(f"\n  {C.YELLOW}New folder path{C.RESET}: ").strip().strip('"')
    if not new_path:
        cprint("  No change made.", C.DIM); return
    if not os.path.isabs(new_path):
        cprint("  Error: Please enter a full path (e.g. C:\\Users\\...)", C.RED); return
    try:
        update_dirs(new_path)
        _update_settings_file("output_folder", new_path)
        cprint(f"\n  Output folder changed to: {BASE_DIR}", C.GREEN + C.BOLD)
        cprint("  Saved to settings.txt.", C.GREEN)
        log("Output folder changed", BASE_DIR)
    except Exception as e:
        cprint(f"  Error: {e}", C.RED)

def _open_file_in_editor(filepath):
    """Open a file in the default text editor, cross-platform."""
    import subprocess, sys
    try:
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe", filepath])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-t", filepath])
        else:
            # Linux -- try common editors in order
            for editor in ["xdg-open", "gedit", "nano", "vi"]:
                try:
                    subprocess.Popen([editor, filepath])
                    return True
                except FileNotFoundError:
                    continue
            cprint("  Could not find a text editor. Open manually:", C.YELLOW)
            cprint(f"  {filepath}", C.DIM)
            return False
        return True
    except Exception as e:
        cprint(f"  Could not open editor: {e}", C.RED)
        cprint(f"  Open manually: {filepath}", C.DIM)
        return False

def _open_settings_file():
    cprint(f"\n  Settings file: {SETTINGS_FILE}", C.CYAN)
    if _open_file_in_editor(SETTINGS_FILE):
        cprint("  Restart the app to apply any changes.", C.YELLOW)

def _update_settings_file(key, value):
    """Update a single key in settings.txt."""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped == f"{key}=":
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}\n")
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        cprint(f"  Warning: Could not update settings.txt: {e}", C.YELLOW)

# ==============================================================================
#  MAIN MENU
# ==============================================================================

class _AppExit(Exception):
    """Raised to exit the app cleanly from any menu depth."""
    pass


def _quit():
    """Clean shutdown — works from any menu depth."""
    if ONLINE_STATE["active"]:
        stop_online_mode()
    log("App closed")
    slow_print("\n  Bye!", C.GREEN + C.BOLD)
    raise _AppExit()


def _check_scram(choice):
    """Return True if user typed scram and it was handled."""
    if choice == "scram":
        scram()
        return True
    if choice in ("quit", "exit", "8"):
        _quit()
        return True
    return False


def scram():
    """Delete all output folders, log file, and settings file."""
    cprint("\n" + "=" * 45, C.RED)
    cprint("  SCRAM -- DELETE EVERYTHING", C.RED + C.BOLD)
    cprint("=" * 45, C.RED)
    cprint("\n  This will permanently delete:", C.YELLOW)
    for folder in [AUDIO_DIR, TXT_DIR, FILES_DIR, KEYS_DIR, INFILES_DIR]:
        cprint(f"    {folder}", C.DIM)
    for f in [LOG_FILE, SETTINGS_FILE]:
        if os.path.exists(f):
            cprint(f"    {f}", C.DIM)
    cprint("\n  This cannot be undone!\n", C.RED)

    confirm = input(f"  {C.YELLOW}Are you sure? (y/n){C.RESET}: ").strip().lower()
    if confirm != "y":
        cprint("  Cancelled.", C.DIM)
        return

    import shutil
    deleted = []
    failed  = []

    # Delete output folders
    for folder in [AUDIO_DIR, TXT_DIR, FILES_DIR, KEYS_DIR, INFILES_DIR]:
        try:
            if os.path.exists(folder):
                shutil.rmtree(folder)
                deleted.append(folder)
        except Exception as e:
            failed.append(f"{folder}: {e}")

    # Delete log file
    for filepath in [LOG_FILE, SETTINGS_FILE]:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                deleted.append(filepath)
        except Exception as e:
            failed.append(f"{filepath}: {e}")

    time.sleep(0.1)
    if deleted:
        cprint(f"\n  Deleted {len(deleted)} item(s):", C.GREEN + C.BOLD)
        for f in deleted:
            cprint(f"    {f}", C.DIM)

    if failed:
        cprint(f"\n  Failed to delete {len(failed)} item(s):", C.RED)
        for f in failed:
            cprint(f"    {f}", C.RED)

    cprint("\n  Done. Folders and settings will be recreated on next run.", C.YELLOW)
    time.sleep(0.3)
    _quit()


def main():
    # Load and apply settings.txt FIRST
    values, out_folder, infiles_folder, log_file_path = parse_settings_file()
    apply_settings_file(values)

    # Apply log file path
    if log_file_path and os.path.isabs(log_file_path):
        set_log_file(log_file_path)

    # Apply folder paths from settings -- default is next to EXE/script
    base = out_folder if (out_folder and os.path.isabs(out_folder)) else SCRIPT_DIR
    update_dirs(base, infiles_folder if (infiles_folder and os.path.isabs(infiles_folder)) else "")

    # Title
    slow_print("=" * 45, C.CYAN)
    slow_print("      BINARY <-> SOUND CONVERTER", C.CYAN + C.BOLD)
    slow_print("         by  PlofOS Group", C.YELLOW)
    slow_print("=" * 45, C.CYAN)
    time.sleep(0.1)

    # Show settings.txt errors if any
    if SETTINGS_ERRORS:
        cprint("\n  WARNING -- Issues found in settings.txt:", C.YELLOW + C.BOLD)
        for err in SETTINGS_ERRORS:
            cprint(f"  {err}", C.YELLOW)
        cprint("  The app will use defaults for any broken values.\n", C.DIM)
        time.sleep(0.3)

    cprint("  Tip: there may be more than meets the eye...", C.DIM)
    cprint(f"  Output : {BASE_DIR}", C.DIM)
    cprint(f"  Infiles: {INFILES_DIR}", C.DIM)
    cprint(f"  Log    : {LOG_FILE}", C.DIM)
    time.sleep(0.2)

    log("App started", f"Output={BASE_DIR}")

    configure_settings()

    try:
        while True:
            time.sleep(0.1)
            cprint("\n" + "=" * 45, C.CYAN)
            header = "        MAIN MENU"
            if ONLINE_STATE["active"]:
                peers = len(ONLINE_STATE["peers"])
                header = f"   MAIN MENU  {C.GREEN}[ONLINE -- {peers} peer(s)]{C.RESET}"
            if SETTINGS["row_mode"]:
                header += f"  {C.YELLOW}[ROW MODE ON]{C.RESET}"
            cprint(header, C.CYAN + C.BOLD)
            cprint("=" * 45, C.CYAN)

            # Check inbox if online
            if ONLINE_STATE["active"]:
                check_inbox()
            cprint(f"  {C.CYAN}1{C.RESET} - Binary -> Sound",  delay=0.03)
            cprint(f"  {C.CYAN}2{C.RESET} - Sound -> Binary",  delay=0.03)
            cprint(f"  {C.CYAN}3{C.RESET} - File Tools",      delay=0.03)
            cprint(f"  {C.CYAN}4{C.RESET} - Settings",        delay=0.03)
            cprint(f"  {C.CYAN}5{C.RESET} - Online Mode",     delay=0.03)
            cprint(f"  {C.CYAN}8{C.RESET} - Quit",            delay=0.03)
            cprint(f"  {C.DIM}Type 'infiles' for quick access. Type 'scram' to wipe all data.{C.RESET}", delay=0.03)

            choice = input(f"\n  {C.YELLOW}Enter a number{C.RESET}: ").strip().lower()

            if choice == "8":
                _quit()
            elif choice == "1":       logaction("Entered Binary->Sound menu"); menu_binary_to_sound()
            elif choice == "2":       logaction("Entered Sound->Binary menu"); menu_sound_to_binary()
            elif choice == "3":       logaction("Entered File Tools menu"); menu_file_tools()
            elif choice == "4":       logaction("Entered Settings menu"); menu_settings()
            elif choice == "5":       logaction("Entered Online Mode menu"); menu_online()
            elif choice == "infiles": browse_infiles()
            elif choice == "scram":   scram()
            else:
                cprint("  Please enter 1, 2, 3, 4, 5, or 8.", C.RED)

    except _AppExit:
        pass

if __name__ == "__main__":
    main()
