#!/data/data/com.termux/files/usr/bin/bash
# Finds people on your list who texted back stop / remove me, and offers to add them to the never-text list.
. "$(dirname "$0")/common.sh"
[ -f list.csv ] || { echo "No list yet. Tap Text-0-Choose-list first."; pause; exit 1; }
python3 android/scan_replies.py list.csv --suppression do_not_text.csv
echo; pause
