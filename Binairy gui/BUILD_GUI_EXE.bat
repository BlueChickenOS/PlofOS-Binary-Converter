@echo off
cd /d "%~dp0"
echo ================================================
echo   BinarySoundConverter GUI - Build EXE
echo   by PlofOS Group
echo ================================================
echo.
echo Step 1: Installing pyinstaller...
python -m pip install pyinstaller
echo.
echo Step 2: Building GUI EXE...
python -m PyInstaller --onefile --windowed --name "BinarySoundConverterGUI" ^
  "binary_sound_gui.py"
echo.
echo Step 3: Copying to current folder...
copy /Y "dist\BinarySoundConverterGUI.exe" "BinarySoundConverterGUI.exe"
echo.
echo Step 4: Cleaning up...
rmdir /S /Q build
rmdir /S /Q dist
if exist "BinarySoundConverterGUI.spec" del /Q "BinarySoundConverterGUI.spec"
echo.
echo ================================================
echo   Done! BinarySoundConverterGUI.exe is here.
echo   Keep binary_sound.py in the same folder!
echo ================================================
pause
