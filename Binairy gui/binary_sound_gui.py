"""
BinarySoundConverter - GUI wrapper
Requires: binary_sound.py in the same folder
"""

import tkinter as tk
from tkinter import font as tkfont
import subprocess, threading, os, sys, time, queue, re

# ── HIDE CONSOLE ON WINDOWS ───────────────────────────────────────────────────
if sys.platform == "win32" and "pythonw" not in sys.executable.lower():
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if os.path.exists(pythonw):
        subprocess.Popen([pythonw] + sys.argv, creationflags=0x00000008)
        sys.exit()

# ── COLOURS ───────────────────────────────────────────────────────────────────
BG_DARK     = "#0a0f1a"
BG_PANEL    = "#0d1526"
BG_TERM     = "#080d18"
ACCENT      = "#1a6fff"
ACCENT_DIM  = "#0f3a8a"
TEXT_BRIGHT = "#c8d8f0"
TEXT_DIM    = "#4a6080"
TEXT_GREEN  = "#2ecc71"
TEXT_YELLOW = "#f39c12"
TEXT_RED    = "#e74c3c"
BORDER      = "#1a2a45"

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
TERM_SCRIPT = os.path.join(SCRIPT_DIR, "binary_sound.py")
LOG_FILE    = os.path.join(SCRIPT_DIR, "bsc_log.txt")
FOLDERS     = {
    "Audio":        os.path.join(SCRIPT_DIR, "Audio"),
    "TextFiles":    os.path.join(SCRIPT_DIR, "TextFiles"),
    "RebuiltFiles": os.path.join(SCRIPT_DIR, "RebuiltFiles"),
    "Keys":         os.path.join(SCRIPT_DIR, "Keys"),
    "Infiles":      os.path.join(SCRIPT_DIR, "Infiles"),
}

_ANSI = re.compile(r'\x1b\[[0-9;]*[mKJH]?')
strip_ansi = lambda t: _ANSI.sub('', t)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BinarySoundConverter  -  PlofOS Group")
        self.configure(bg=BG_DARK)
        self.geometry("1280x760")
        self.minsize(1000, 580)

        self._q       = queue.Queue()
        self._history = []
        self._hidx    = -1
        self._proc    = None

        self._build_fonts()
        self._build_ui()
        self._ensure_settings()
        self._launch()
        self._watch_log()
        self._watch_folders()

        self.protocol("WM_DELETE_WINDOW", self._close)

        # Focus entry reliably after window is shown
        self.update()
        self._entry.focus_set()

    # ── FONTS ─────────────────────────────────────────────────────────────────

    def _build_fonts(self):
        self.fmono  = tkfont.Font(family="Consolas", size=11)
        self.fsmall = tkfont.Font(family="Consolas", size=9)
        self.fbold  = tkfont.Font(family="Consolas", size=10, weight="bold")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # title bar
        bar = tk.Frame(self, bg=ACCENT_DIM, height=30)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Label(bar, text="  BINARY SOUND CONVERTER  -  PlofOS Group",
                 bg=ACCENT_DIM, fg=TEXT_BRIGHT, font=self.fbold,
                 anchor="w").pack(side=tk.LEFT, padx=6)
        self._status = tk.Label(bar, text="OFFLINE", bg=ACCENT_DIM,
                                fg=TEXT_DIM, font=self.fsmall)
        self._status.pack(side=tk.RIGHT, padx=10)

        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # left (folders)
        left = tk.Frame(body, bg=BG_DARK, width=175)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))
        left.pack_propagate(False)
        self._build_folders(left)

        # right (log + online)
        right = tk.Frame(body, bg=BG_DARK, width=245)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)
        self._build_log(right)
        self._build_online(right)

        # center (terminal)
        center = tk.Frame(body, bg=BG_DARK)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self._build_terminal(center)

    # ── panel helper ──────────────────────────────────────────────────────────

    def _panel(self, parent, title, fixed=False):
        outer = tk.Frame(parent, bg=BORDER)
        if fixed:
            outer.pack(fill=tk.X, pady=(0, 4))
        else:
            outer.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        hdr = tk.Frame(outer, bg=ACCENT_DIM, height=20)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text=f"  {title}", bg=ACCENT_DIM, fg=TEXT_BRIGHT,
                 font=self.fbold, anchor="w").pack(side=tk.LEFT)
        inner = tk.Frame(outer, bg=BG_PANEL, padx=4, pady=3)
        inner.pack(fill=tk.BOTH, expand=True)
        return inner

    # ── 1 folders ─────────────────────────────────────────────────────────────

    def _build_folders(self, parent):
        inner = self._panel(parent, "1  Folders")
        self._fcounts = {}
        self._folder_frames = {}

        for name, path in FOLDERS.items():
            # Container for each folder section
            section = tk.Frame(inner, bg=BG_PANEL)
            section.pack(fill=tk.X, pady=(0, 2))

            # Folder button header
            btn = tk.Button(
                section, text=f"  + {name}",
                bg=BG_DARK, fg=TEXT_BRIGHT,
                font=self.fsmall, activebackground=ACCENT_DIM,
                activeforeground=TEXT_BRIGHT, relief=tk.FLAT,
                anchor="w", cursor="hand2",
                command=lambda n=name, p=path, s=section: self._toggle_folder(n, p, s))
            btn.pack(fill=tk.X)
            btn.bind("<Enter>", lambda e, w=btn: w.config(bg=ACCENT_DIM))
            btn.bind("<Leave>", lambda e, w=btn: w.config(bg=BG_DARK))

            # File list frame (hidden by default)
            file_frame = tk.Frame(section, bg=BG_PANEL)
            # NOT packed yet — shown on click

            self._folder_frames[name] = {
                "btn":        btn,
                "frame":      file_frame,
                "expanded":   False,
                "path":       path,
            }

            # Count label
            lbl = tk.Label(inner, text=f"  {name}: -",
                           bg=BG_PANEL, fg=TEXT_DIM,
                           font=self.fsmall, anchor="w")
            lbl.pack(fill=tk.X)
            self._fcounts[name] = lbl

    def _toggle_folder(self, name, path, section):
        info  = self._folder_frames[name]
        btn   = info["btn"]
        frame = info["frame"]

        if info["expanded"]:
            # Collapse
            frame.pack_forget()
            btn.config(text=f"  + {name}")
            info["expanded"] = False
        else:
            # Expand — build file list
            for widget in frame.winfo_children():
                widget.destroy()

            os.makedirs(path, exist_ok=True)
            try:
                files = [f for f in os.listdir(path)
                         if os.path.isfile(os.path.join(path, f))]
            except Exception:
                files = []

            if not files:
                tk.Label(frame, text="    (empty)", bg=BG_PANEL,
                         fg=TEXT_DIM, font=self.fsmall,
                         anchor="w").pack(fill=tk.X, padx=4)
            else:
                for fname in sorted(files):
                    fpath = os.path.join(path, fname)
                    try:
                        size  = os.path.getsize(fpath)
                        ext   = os.path.splitext(fname)[1].upper() or "FILE"
                        if size < 1024:
                            sstr = f"{size} B"
                        elif size < 1024 * 1024:
                            sstr = f"{size/1024:.1f} KB"
                        else:
                            sstr = f"{size/1024/1024:.1f} MB"
                    except Exception:
                        ext  = "?"
                        sstr = "?"

                    # File entry frame
                    entry = tk.Frame(frame, bg=BG_DARK, pady=2)
                    entry.pack(fill=tk.X, padx=2, pady=1)

                    # Top row: name  type  size
                    top = tk.Frame(entry, bg=BG_DARK)
                    top.pack(fill=tk.X, padx=4)

                    tk.Label(top, text=fname,
                             bg=BG_DARK, fg=TEXT_BRIGHT,
                             font=self.fsmall, anchor="w").pack(side=tk.LEFT)
                    tk.Label(top, text=f"  {ext}  {sstr}",
                             bg=BG_DARK, fg=TEXT_DIM,
                             font=self.fsmall, anchor="e").pack(side=tk.RIGHT)

                    # Bottom row: full path (selectable)
                    path_var = tk.StringVar(value=fpath)
                    path_entry = tk.Entry(
                        entry, textvariable=path_var,
                        bg=BG_DARK, fg=ACCENT,
                        font=self.fsmall, relief=tk.FLAT,
                        bd=0, state="readonly",
                        readonlybackground=BG_DARK,
                        selectbackground=ACCENT_DIM,
                        selectforeground=TEXT_BRIGHT)
                    path_entry.pack(fill=tk.X, padx=4)

                    # Hover highlight
                    entry.bind("<Enter>",
                               lambda e, w=entry: w.config(bg=ACCENT_DIM))
                    entry.bind("<Leave>",
                               lambda e, w=entry: w.config(bg=BG_DARK))
                    for child in (top,) + tuple(top.winfo_children()) + (path_entry,):
                        try:
                            child.bind("<Enter>",
                                       lambda e, w=entry: w.config(bg=ACCENT_DIM))
                            child.bind("<Leave>",
                                       lambda e, w=entry: w.config(bg=BG_DARK))
                        except Exception:
                            pass

            frame.pack(fill=tk.X, padx=2)
            btn.config(text=f"  - {name}")
            info["expanded"] = True

    def _watch_folders(self):
        def run():
            while True:
                for name, path in FOLDERS.items():
                    try:
                        n = len([f for f in os.listdir(path)
                                 if os.path.isfile(os.path.join(path, f))]) \
                            if os.path.exists(path) else 0
                        fg = TEXT_BRIGHT if n else TEXT_DIM
                        self.after(0, self._fcounts[name].config,
                                   {"text": f"  {name}: {n} file(s)", "fg": fg})
                    except Exception:
                        pass
                time.sleep(4)
        threading.Thread(target=run, daemon=True).start()

    def _build_terminal(self, parent):
        inner = self._panel(parent, "2  Terminal")

        # input row FIRST (at bottom) so it never gets pushed off
        input_frame = tk.Frame(inner, bg=BG_TERM)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(3, 0))

        tk.Frame(inner, bg=BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)

        tk.Label(input_frame, text=" >", bg=BG_TERM, fg=ACCENT,
                 font=self.fmono).pack(side=tk.LEFT)

        self._var   = tk.StringVar()
        self._entry = tk.Entry(
            input_frame,
            textvariable=self._var,
            bg=BG_TERM,
            fg=TEXT_BRIGHT,
            insertbackground=TEXT_BRIGHT,
            selectbackground=ACCENT_DIM,
            selectforeground=TEXT_BRIGHT,
            relief=tk.FLAT,
            bd=2,
            font=self.fmono,
            highlightthickness=2,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self._entry.bind("<Return>", self._submit)
        self._entry.bind("<Up>",     self._hist_up)
        self._entry.bind("<Down>",   self._hist_dn)
        self._entry.bind("<Escape>", lambda e: self._var.set(""))

        # output area fills the rest ABOVE the input
        self._out = tk.Text(
            inner, bg=BG_TERM, fg=TEXT_BRIGHT, font=self.fmono,
            relief=tk.FLAT, bd=0, wrap=tk.WORD, state=tk.DISABLED,
            cursor="arrow", takefocus=0)
        self._out.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # colour tags
        self._out.tag_configure("g", foreground=TEXT_GREEN)
        self._out.tag_configure("y", foreground=TEXT_YELLOW)
        self._out.tag_configure("r", foreground=TEXT_RED)
        self._out.tag_configure("d", foreground=TEXT_DIM)
        self._out.tag_configure("a", foreground=ACCENT)
        self._out.tag_configure("w", foreground=TEXT_BRIGHT)

        self._out.bind("<Button-1>", lambda e: self._entry.focus_set())

    def _submit(self, event=None):
        text = self._var.get()
        self._var.set("")
        self._append(f"> {text}\n", "a")
        if text.strip():
            self._history.append(text)
        self._hidx = -1
        self._q.put(text + "\n")
        return "break"

    def _hist_up(self, event=None):
        if not self._history:
            return "break"
        self._hidx = min(self._hidx + 1, len(self._history) - 1)
        self._var.set(self._history[-(self._hidx + 1)])
        self._entry.icursor(tk.END)
        return "break"

    def _hist_dn(self, event=None):
        if self._hidx <= 0:
            self._hidx = -1
            self._var.set("")
            return "break"
        self._hidx -= 1
        self._var.set(self._history[-(self._hidx + 1)])
        self._entry.icursor(tk.END)
        return "break"

    def _append(self, text, tag="w"):
        """Thread-safe write to output area."""
        self._out.configure(state=tk.NORMAL)
        self._out.insert(tk.END, text, tag)
        self._out.see(tk.END)
        self._out.configure(state=tk.DISABLED)

    def _tag_for(self, line):
        l = line.lower()
        if any(w in l for w in ("error", "failed", "invalid", "could not")): return "r"
        if any(w in l for w in ("warning", "skipped")):                       return "y"
        if any(w in l for w in ("saved", "done!", "sent", "online")):         return "g"
        if any(w in l for w in ("tip:", "output :", "log    :")):             return "d"
        if "=====" in line or "-----" in line:                                 return "a"
        return "w"

    # ── 3 log ─────────────────────────────────────────────────────────────────

    def _build_log(self, parent):
        inner = self._panel(parent, "3  Recent Log", fixed=True)
        self._log = tk.Text(
            inner, bg=BG_PANEL, fg=TEXT_DIM, font=self.fsmall,
            relief=tk.FLAT, bd=0, wrap=tk.WORD, state=tk.DISABLED,
            height=10, takefocus=0)
        self._log.pack(fill=tk.BOTH, expand=True)
        self._log.tag_configure("a", foreground=ACCENT)
        self._log.tag_configure("b", foreground=TEXT_BRIGHT)
        self._log.bind("<Button-1>", lambda e: self._entry.focus_set())

    def _log_write(self, lines):
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        for ln in lines[-20:]:
            t = "a" if "ACTION" in ln else "b"
            self._log.insert(tk.END, ln + "\n", t)
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    # ── 4 online ──────────────────────────────────────────────────────────────

    def _build_online(self, parent):
        inner = self._panel(parent, "4  Online Mode")
        self._onlbl = tk.Label(inner, text="Offline", bg=BG_PANEL,
                               fg=TEXT_DIM, font=self.fbold, anchor="w")
        self._onlbl.pack(fill=tk.X, pady=(0, 3))
        tk.Frame(inner, bg=BORDER, height=1).pack(fill=tk.X, pady=2)
        tk.Label(inner, text="Peers:", bg=BG_PANEL, fg=TEXT_DIM,
                 font=self.fsmall, anchor="w").pack(fill=tk.X)
        self._peers = tk.Text(inner, bg=BG_PANEL, fg=TEXT_BRIGHT,
                              font=self.fsmall, relief=tk.FLAT, bd=0,
                              height=5, state=tk.DISABLED, takefocus=0)
        self._peers.pack(fill=tk.X, pady=(2, 4))
        tk.Frame(inner, bg=BORDER, height=1).pack(fill=tk.X, pady=2)
        tk.Label(inner, text="Inbox:", bg=BG_PANEL, fg=TEXT_DIM,
                 font=self.fsmall, anchor="w").pack(fill=tk.X)
        self._inbox = tk.Text(inner, bg=BG_PANEL, fg=TEXT_YELLOW,
                              font=self.fsmall, relief=tk.FLAT, bd=0,
                              height=5, state=tk.DISABLED, takefocus=0)
        self._inbox.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        for w in (self._peers, self._inbox):
            w.bind("<Button-1>", lambda e: self._entry.focus_set())

    def _online_update(self, lines):
        active, peers, inbox = False, [], []
        for ln in lines[-150:]:
            if "Online mode started"   in ln: active=True;  peers=[];inbox=[]
            elif "Online mode stopped" in ln: active=False; peers=[]
            elif "Peer discovered"     in ln:
                p = ln.split("|")[-1].strip() if "|" in ln else ""
                if p and p not in peers: peers.append(p)
            elif "Received network" in ln or "Call ID received" in ln:
                inbox.append(ln[:19] if len(ln)>19 else ln)

        self._onlbl.config(
            text=f"Online  ({len(peers)} peers)" if active else "Offline",
            fg=TEXT_GREEN if active else TEXT_DIM)
        self._status.config(
            text=f"ONLINE  {len(peers)} peer(s)" if active else "OFFLINE",
            fg=TEXT_GREEN if active else TEXT_DIM)

        for widget, items, empty in [
            (self._peers, peers[-5:], "No peers yet"),
            (self._inbox, inbox[-5:], "No messages"),
        ]:
            widget.configure(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert(tk.END,
                "\n".join(f"  {x}" for x in items) if items else f"  {empty}")
            widget.configure(state=tk.DISABLED)

    # ── PROCESS ───────────────────────────────────────────────────────────────

    def _launch(self):
        if not os.path.exists(TERM_SCRIPT):
            self._append(
                f"ERROR: binary_sound.py not found in:\n  {SCRIPT_DIR}\n\n"
                "Place binary_sound.py in the same folder as this GUI file.\n", "r")
            return

        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW

        self._proc = subprocess.Popen(
            [sys.executable, "-u", TERM_SCRIPT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=SCRIPT_DIR, bufsize=0,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
            **kw)

        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._sender, daemon=True).start()

    def _reader(self):
        import io
        buf = ""
        while True:
            try:
                ch = self._proc.stdout.read(1)
                if not ch:
                    break
                c = ch.decode("utf-8", errors="replace")
                buf += c

                # Flush on newline or prompt endings
                if c == "\n" or buf.endswith(": ") or buf.endswith("? "):
                    clean = strip_ansi(buf)
                    if clean.strip():
                        self.after(0, self._append, clean, self._tag_for(clean))
                    buf = ""
                # Also flush if buffer is getting long (slow_print chars)
                elif len(buf) > 80:
                    clean = strip_ansi(buf)
                    if clean.strip():
                        self.after(0, self._append, clean, self._tag_for(clean))
                    buf = ""
            except Exception:
                break
        if buf.strip():
            clean = strip_ansi(buf)
            self.after(0, self._append, clean, self._tag_for(clean))
        self.after(0, self._append, "\n[Process ended]\n", "d")

    def _sender(self):
        while True:
            try:
                text = self._q.get()
                self._proc.stdin.write(text.encode("utf-8"))
                self._proc.stdin.flush()
            except Exception:
                break

    # ── WATCHERS ──────────────────────────────────────────────────────────────

    def _watch_log(self):
        def run():
            while True:
                try:
                    if os.path.exists(LOG_FILE):
                        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                            lines = f.read().splitlines()
                        self.after(0, self._log_write, lines)
                        self.after(0, self._online_update, lines)
                except Exception:
                    pass
                time.sleep(2)
        threading.Thread(target=run, daemon=True).start()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _ensure_settings(self):
        p = os.path.join(SCRIPT_DIR, "settings.txt")
        if os.path.exists(p):
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write("# BinarySoundConverter Settings\n"
                        "output_folder=\ninfiles_folder=\nlog_file=\n"
                        "freq_zero=440\nfreq_one=880\ntone_duration=0.01\n"
                        "volume=0.5\nheader_freq_zero=300\nheader_freq_one=600\n"
                        "header_tone_duration=0.05\nrow_mode=false\n"
                        "row1_freq_zero=400\nrow1_freq_one=800\n"
                        "row2_freq_zero=500\nrow2_freq_one=900\n"
                        "row3_freq_zero=600\nrow3_freq_one=1000\n"
                        "lock_freq_zero=false\nlock_freq_one=false\n"
                        "lock_tone_duration=false\nlock_volume=false\n")
        except Exception:
            pass

    def _close(self):
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
