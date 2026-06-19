#!/bin/bash
# BinarySoundConverter GUI - Build script for Linux
# by PlofOS Group
# Run with: bash BUILD_GUI_LINUX.sh

cd "$(dirname "$0")"

echo "================================================"
echo "  BinarySoundConverter GUI - Build for Linux"
echo "  by PlofOS Group"
echo "================================================"
echo ""

echo "Step 1: Installing dependencies..."
if command -v apt-get &> /dev/null; then
    sudo apt-get install -y portaudio19-dev python3-tk ffmpeg
elif command -v dnf &> /dev/null; then
    sudo dnf install -y portaudio-devel python3-tkinter ffmpeg
elif command -v pacman &> /dev/null; then
    sudo pacman -S --noconfirm portaudio tk ffmpeg
else
    echo "  Could not detect package manager. Install dependencies manually."
fi
echo ""

echo "Step 2: Installing Python libraries..."
pip3 install numpy sounddevice scipy soundfile pyinstaller
echo ""

echo "Step 3: Building GUI executable..."
python3 -m PyInstaller --onefile --windowed \
  --name "BinarySoundConverterGUI" \
  --hidden-import sounddevice \
  --hidden-import soundfile \
  --hidden-import numpy \
  --hidden-import scipy \
  --hidden-import cffi \
  --hidden-import tkinter \
  "binary_sound_gui.py"
echo ""

echo "Step 4: Copying to current folder..."
cp "dist/BinarySoundConverterGUI" "BinarySoundConverterGUI"
chmod +x "BinarySoundConverterGUI"
echo ""

echo "Step 5: Cleaning up..."
rm -rf build dist BinarySoundConverterGUI.spec
echo ""

echo "================================================"
echo "  Done! Run with: ./BinarySoundConverterGUI"
echo "  Keep binary_sound.py in the same folder!"
echo "================================================"
