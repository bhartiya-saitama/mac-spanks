#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Spank Detector"
SRC_ENTRY="src/app.py"
CONFIG_PATH="src/config.json"
ICON_PATH="assets/icon.png"
SAMPLE_AUDIO="assets/faah_sound.mp3"
DISTPATH="dist"

echo "==> Spank Detector: one-command build"

# ----------------------------
# 0) Sanity checks
# ----------------------------
if [[ ! -f "$SRC_ENTRY" ]]; then
  echo "ERROR: Cannot find $SRC_ENTRY"
  exit 1
fi

if [[ ! -f "requirements.txt" ]]; then
  echo "ERROR: Cannot find requirements.txt"
  exit 1
fi

if [[ ! -f "$ICON_PATH" ]]; then
  echo "WARNING: Icon not found at $ICON_PATH (app will build without custom icon)"
  ICON_FLAG=()
else
  ICON_FLAG=(--icon "$ICON_PATH")
fi

# ----------------------------
# 1) Homebrew deps
# ----------------------------
if command -v brew >/dev/null 2>&1; then
  echo "==> Ensuring Homebrew deps"
  brew update >/dev/null || true
  brew install portaudio >/dev/null || true
else
  echo "WARNING: Homebrew not found. If sounddevice fails, install brew + portaudio."
fi

# ----------------------------
# 2) Create venv if needed
# ----------------------------
if [[ ! -f "bin/activate" ]]; then
  echo "==> Creating venv"
  python3 -m venv .
else
  echo "==> Venv already exists, skipping creation"
fi

# shellcheck disable=SC1091
source "bin/activate"

echo "==> Upgrading pip"
python -m pip install --upgrade pip >/dev/null

# ----------------------------
# 3) Install Python deps
# ----------------------------
echo "==> Installing Python requirements"
pip install -r requirements.txt

echo "==> Installing PyInstaller"
pip install pyinstaller

# ----------------------------
# 4) Clean old builds
# ----------------------------
echo "==> Cleaning old build artifacts"
rm -rf build dist "${APP_NAME}.spec" 2>/dev/null || true

# # ----------------------------
# # 5) Revoke microphone permission from Info.plist
# # ----------------------------
# echo "==> Revoking microphone permission from Info.plist"
# tccutil reset Microphone $APP_NAME

# ----------------------------
# 6) Build the app bundle
# ----------------------------
echo "==> Building .app with PyInstaller"

# Bundle the default config.json into the app so ConfigManager can seed user config on first run.
# NOTE: On macOS, the --add-data separator is ":".
pyinstaller \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  "${ICON_FLAG[@]}" \
  --add-data "$CONFIG_PATH:." \
  --add-data "$ICON_PATH:." \
  --add-data "$SAMPLE_AUDIO:." \
  "$SRC_ENTRY"

# ----------------------------
# 7) Inject microphone permission into Info.plist
# ----------------------------
PLIST="dist/${APP_NAME}.app/Contents/Info.plist"
echo "==> Adding NSMicrophoneUsageDescription to Info.plist"
/usr/libexec/PlistBuddy \
  -c "Add :NSMicrophoneUsageDescription string 'Spank Detector needs microphone access to detect chassis taps.'" \
  "$PLIST"

# ----------------------------
# 8) Ad-hoc code sign the app
# NOTE: This is necessary to allow the app to access the microphone.
# ----------------------------
echo "==> Ad-hoc signing the app"
codesign --force --deep --sign - "dist/${APP_NAME}.app"

echo ""
echo "Build complete. .app is in ${DISTPATH}/${APP_NAME}.app"