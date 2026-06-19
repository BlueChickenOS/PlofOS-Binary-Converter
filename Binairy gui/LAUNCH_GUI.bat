@echo off
cd /d "%~dp0"

:: Try pythonw first (runs without console window)
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "binary_sound_gui.py"
    exit
)

:: Fall back to python with hidden window
python "binary_sound_gui.py"
