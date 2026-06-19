# PlofOS-Binary-Converter
A Binary Converter that can make .wav, MP3 and txt documents from any file. It can rebuild the file when needed and has a friendly setup and is easy to use. Note that this is made with AI and is part of a project and is for the point of testing and playing around with Claude.

Install file:

================================================
   BINARY SOUND CONVERTER -- INSTALL GUIDE
                by PlofOS Group
================================================

Two versions are available:
  - Terminal version (binary_sound.py)
  - GUI version     (binary_sound_gui.py)

Both need binary_sound.py in the same folder.
The GUI is a wrapper around the terminal version.


================================================
 WINDOWS -- TERMINAL VERSION
================================================

------------------------------------------------
 STEP 1 -- Install Python
------------------------------------------------

  python --version

  Should show Python 3.x.x
  Download from https://python.org if missing.
  IMPORTANT: tick "Add Python to PATH" during
  installation or nothing will work.


------------------------------------------------
 STEP 2 -- Install libraries
------------------------------------------------

  python -m pip install numpy
  python -m pip install sounddevice
  python -m pip install scipy
  python -m pip install soundfile
  python -m pip install pyinstaller


------------------------------------------------
 STEP 3 -- Run as script
------------------------------------------------

  python "C:\path\to\binary_sound.py"

Use quotes if your path contains spaces.


------------------------------------------------
 STEP 4 -- Build EXE (recommended)
------------------------------------------------

Put binary_sound.py and BUILD_EXE.bat in the
same folder. Double-click BUILD_EXE.bat.

  -> Installs all libraries automatically
  -> Builds BinarySoundConverter.exe
  -> Copies EXE to the same folder
  -> Cleans up all build files

Double-click BinarySoundConverter.exe to run.
No Python needed after building!


------------------------------------------------
 STEP 5 (OPTIONAL) -- Enable MP3
------------------------------------------------

  1. Go to https://ffmpeg.org/download.html
  2. Download the Windows build
  3. Extract the zip file
  4. Add the "bin" folder to your system PATH

WAV works perfectly fine without ffmpeg.


================================================
 WINDOWS -- GUI VERSION
================================================

Requires binary_sound.py in the same folder!

------------------------------------------------
 Run the GUI
------------------------------------------------

Double-click LAUNCH_GUI.bat

This uses pythonw.exe (no console window).
The GUI opens with 4 panels:
  1 - Folder browser (click to expand/collapse)
  2 - Terminal (type in the > box at bottom)
  3 - Recent log
  4 - Online mode status


------------------------------------------------
 Build GUI EXE
------------------------------------------------

Double-click BUILD_GUI_EXE.bat

Creates BinarySoundConverterGUI.exe
Keep binary_sound.py in the same folder!


------------------------------------------------
 WINDOWS FIREWALL -- ONLINE MODE
------------------------------------------------

First time using Online Mode, Windows Firewall
may ask for permission. Click "Allow" on both
Private and Public networks.

Open ports manually if needed:
  UDP 55400 -- peer discovery
  TCP 55401 -- data transfer


================================================
 LINUX -- TERMINAL VERSION
================================================

------------------------------------------------
 STEP 1 -- Install Python
------------------------------------------------

Python 3 is usually pre-installed. Check with:

  python3 --version

If missing:
  sudo apt-get install python3 python3-pip   # Debian/Ubuntu
  sudo dnf install python3 python3-pip       # Fedora/RHEL
  sudo pacman -S python python-pip           # Arch


------------------------------------------------
 STEP 2 -- Install PortAudio
------------------------------------------------

Required for microphone and audio on Linux:

  sudo apt-get install portaudio19-dev       # Debian/Ubuntu
  sudo dnf install portaudio-devel           # Fedora/RHEL
  sudo pacman -S portaudio                   # Arch


------------------------------------------------
 STEP 3 -- Install libraries
------------------------------------------------

  pip3 install numpy
  pip3 install sounddevice
  pip3 install scipy
  pip3 install soundfile
  pip3 install pyinstaller

If pip3 is not found:
  python3 -m pip install <library>


------------------------------------------------
 STEP 4 -- Run as script
------------------------------------------------

  python3 "/path/to/binary_sound.py"

Or make it executable:
  chmod +x binary_sound.py
  ./binary_sound.py


------------------------------------------------
 STEP 5 -- Build executable
------------------------------------------------

Put binary_sound.py and BUILD_LINUX.sh in the
same folder, then run:

  bash BUILD_LINUX.sh

  -> Installs PortAudio via your package manager
  -> Installs all Python libraries
  -> Builds BinarySoundConverter executable
  -> Copies it to the same folder
  -> Cleans up all build files

Run with:  ./BinarySoundConverter


------------------------------------------------
 STEP 6 (OPTIONAL) -- Enable MP3
------------------------------------------------

  sudo apt-get install ffmpeg               # Debian/Ubuntu
  sudo dnf install ffmpeg                   # Fedora/RHEL
  sudo pacman -S ffmpeg                     # Arch


------------------------------------------------
 LINUX FIREWALL -- ONLINE MODE
------------------------------------------------

  sudo ufw allow 55400/udp
  sudo ufw allow 55401/tcp

Or for firewalld:
  sudo firewall-cmd --add-port=55400/udp --permanent
  sudo firewall-cmd --add-port=55401/tcp --permanent
  sudo firewall-cmd --reload


================================================
 LINUX -- GUI VERSION
================================================

The GUI version works on Linux!
It uses tkinter which runs on all platforms.

------------------------------------------------
 STEP 1 -- Install tkinter
------------------------------------------------

  sudo apt-get install python3-tk           # Debian/Ubuntu
  sudo dnf install python3-tkinter          # Fedora/RHEL
  sudo pacman -S tk                         # Arch


------------------------------------------------
 STEP 2 -- Run the GUI
------------------------------------------------

Put binary_sound.py and binary_sound_gui.py
in the same folder, then run:

  bash LAUNCH_GUI.sh

Or directly:
  python3 binary_sound_gui.py

No console window appears on Linux -- it
opens directly into the GUI.


------------------------------------------------
 STEP 3 -- Build GUI executable (Linux)
------------------------------------------------

  bash BUILD_LINUX.sh

This builds the terminal version only.
To build the GUI as a standalone executable:

  pip3 install pyinstaller
  python3 -m PyInstaller --onefile --windowed \
    --name "BinarySoundConverterGUI" \
    binary_sound_gui.py

The result is in the dist/ folder.
Keep binary_sound.py next to it!


================================================
 FILES NEXT TO THE EXE / SCRIPT
================================================

  settings.txt      Created on first run.
                    Edit to change defaults.
                    Errors shown at startup.
                    Open via Settings -> 4

  bsc_log.txt       Activity log. Rotates at
                    10 MB to bsc_log_old.txt.
                    Records all actions, file
                    paths used, and network
                    activity.

  Audio\            WAV and MP3 files
  TextFiles\        Binary TXT files
  RebuiltFiles\     Files rebuilt from binary
  Keys\             Row mode key file
  Infiles\          Drop files here for quick
                    access via "infiles" command

All folders created automatically on first run.


================================================
 SETTINGS.TXT -- ALL OPTIONS
================================================

Folders:
  output_folder=       Full path or leave blank
  infiles_folder=      Full path or leave blank
  log_file=            Full path to log .txt
                       Leave blank = next to EXE

Audio defaults:
  freq_zero=440        Hz for bit 0
  freq_one=880         Hz for bit 1
  tone_duration=0.01   Seconds per bit
  volume=0.5           0.0 to 1.0

Header block (only editable here):
  header_freq_zero=300
  header_freq_one=600
  header_tone_duration=0.05

Row mode:
  row_mode=false
  row1_freq_zero=400
  row1_freq_one=800
  row2_freq_zero=500
  row2_freq_one=900
  row3_freq_zero=600
  row3_freq_one=1000

Locks:
  lock_freq_zero=false
  lock_freq_one=false
  lock_tone_duration=false
  lock_volume=false

Lines starting with # are comments.
Delete settings.txt to reset to defaults.
Errors shown at startup without crashing.


================================================
 MAIN MENU
================================================

  1 - Binary -> Sound
  2 - Sound -> Binary
  3 - File Tools
  4 - Settings
  5 - Online Mode
  8 - Quit

  Special commands (work in ALL menus):
    Type "infiles" -- quick file access
    Type "scram"   -- emergency delete (see below)


================================================
 SCRAM COMMAND
================================================

Type "scram" at any menu or submenu to trigger
an emergency delete of all data the app created.

What it deletes:
  Audio\          -- all WAV and MP3 files
  TextFiles\      -- all binary TXT files
  RebuiltFiles\   -- all rebuilt files
  Keys\           -- row mode key file
  Infiles\        -- all files in inbox folder
  bsc_log.txt     -- the activity log
  settings.txt    -- all your settings

What it does NOT delete:
  The EXE or script files themselves
  Any files you put there manually from outside

How it works:
  1. Type "scram" at any menu
  2. It shows you exactly what will be deleted
  3. It asks: "Are you sure? (y/n)"
  4. Type "y" to confirm, anything else cancels
  5. All listed items are permanently deleted

After scram:
  Folders are recreated automatically next time
  you save a file or start the app.
  Settings.txt is also recreated with defaults.

WARNING: This cannot be undone. Use with care.



