@echo off
:: Move to the folder where this BAT file lives
cd /d "%~dp0"

echo ================================================
echo   BinarySoundConverter - Build EXE for Windows
echo   by PlofOS Group
echo ================================================
echo.

echo Step 1: Installing required libraries...
python -m pip install numpy sounddevice soundfile scipy pyinstaller
echo.

echo Step 2: Building EXE (this may take a minute)...
python -m PyInstaller --onefile --console --name "BinarySoundConverter" ^
  --hidden-import sounddevice ^
  --hidden-import soundfile ^
  --hidden-import numpy ^
  --hidden-import scipy ^
  --hidden-import cffi ^
  "binary_sound.py"
echo.

echo Step 3: Copying EXE to current folder...
copy /Y "dist\BinarySoundConverter.exe" "BinarySoundConverter.exe"
echo.

echo Step 4: Cleaning up build files...
rmdir /S /Q "build"
rmdir /S /Q "dist"
if exist "BinarySoundConverter.spec" del /Q "BinarySoundConverter.spec"
echo.

echo ================================================
echo   Done! BinarySoundConverter.exe is right here
echo   in this folder. Double-click it to run!
echo ================================================
echo.
pause
