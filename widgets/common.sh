#!/data/data/com.termux/files/usr/bin/bash
# Shared helpers for the home-screen buttons. Sourced by the other scripts.
TOOL="${TEXTTOOL_DIR:-$HOME/text-tool}"
pause() { read -r -p "Press Enter to close" _ || true; }
cd "$TOOL" 2>/dev/null || { echo "Can't find $TOOL. Finish the setup steps first."; pause; exit 1; }
# Use the newest list.csv from Downloads if there is one
[ -f "$HOME/storage/downloads/list.csv" ] && cp -u "$HOME/storage/downloads/list.csv" "$TOOL/list.csv"
[ -f do_not_text.csv ] || echo "Phone" > do_not_text.csv
FLAGS="--suppression do_not_text.csv"
[ -f require_consent.txt ] && FLAGS="$FLAGS --require-consent"
CAMPAIGN="$(cat campaign.txt 2>/dev/null)"; CAMPAIGN="${CAMPAIGN:-mytexts}"
need_ready() {
  [ -f message.txt ] || { echo "No message yet. Tap 'Text-6-Change-message' first."; pause; exit 1; }
  [ -f list.csv ] || { echo "No list.csv found. Save your list in Downloads as list.csv (needs a Phone column)."; pause; exit 1; }
}
