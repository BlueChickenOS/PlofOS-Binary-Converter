#!/bin/bash
# BinarySoundConverter - Build script for Linux
# by PlofOS Group
# Run with: bash BUILD_LINUX.sh

cd "$(dirname "$0")"

echo "================================================"
echo "  BinarySoundConverter - Build for Linux"
echo "  by PlofOS Group"
echo "================================================"
echo ""

echo "Step 1: Installing PortAudio (needed for audio)..."
if command -v apt-get &> /dev/null; then
    sudo apt-get install -y portaudio19-dev python3-tk ffmpeg
elif command -v dnf &> /dev/null; then
    sudo dnf install -y portaudio-devel python3-tkinter ffmpeg
elif command -v pacman &> /dev/null; then
    sudo pacman -S --noconfirm portaudio tk ffmpeg
else
    echo "  Could not detect package manager. Install portaudio manually."
fi
echo ""

echo "Step 2: Installing Python libraries..."
pip3 install numpy sounddevice scipy soundfile pyinstaller
echo ""

echo "Step 3: Building terminal EXE..."
python3 -m PyInstaller --onefile --console \
  --name "BinarySoundConverter" \
  --hidden-import sounddevice \
  --hidden-import soundfile \
  --hidden-import numpy \
  --hidden-import scipy \
  --hidden-import cffi \
  "binary_sound.py"
echo ""

echo "Step 4: Copying to current folder..."
cp "dist/BinarySoundConverter" "BinarySoundConverter"
chmod +x "BinarySoundConverter"
echo ""

echo "Step 5: Cleaning up..."
rm -rf build dist BinarySoundConverter.spec
echo ""

echo "================================================"
echo "  Done! Run with: ./BinarySoundConverter"
echo "================================================"
