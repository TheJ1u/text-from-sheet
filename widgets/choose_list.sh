#!/data/data/com.termux/files/usr/bin/bash
# Opens the phone's file picker. Tap your Excel (.xlsx) or CSV list; it becomes the list the tool uses.
. "$(dirname "$0")/common.sh"
command -v termux-storage-get >/dev/null || { echo "This needs the Termux:API app (and: pkg install termux-api)."; pause; exit 1; }
PICK="$TOOL/.picked_file"
rm -f "$PICK"
echo "Your phone's file picker is opening. Tap your Excel or CSV contact list."
termux-storage-get "$PICK"
# The picked file can arrive a moment later: wait up to 3 minutes for it to finish copying.
for i in $(seq 1 180); do
  if [ -s "$PICK" ]; then
    A=$(wc -c < "$PICK"); sleep 1; B=$(wc -c < "$PICK"); [ "$A" = "$B" ] && break
  else
    sleep 1
  fi
done
[ -s "$PICK" ] || { echo "No file was chosen. Nothing changed."; pause; exit 1; }
if [ "$(head -c 2 "$PICK")" = "PK" ] && ! python3 -c "import openpyxl" 2>/dev/null; then
  echo "Installing the Excel reader (one time)..."
  pip install -q openpyxl || { echo "Couldn't install it. Save the list as CSV instead and choose that."; pause; exit 1; }
fi
python3 tools/pick_list.py "$PICK" list.csv
rm -f "$PICK"
echo
echo "(If you later save a newer list.csv in Downloads, the newest list is the one used.)"
pause
