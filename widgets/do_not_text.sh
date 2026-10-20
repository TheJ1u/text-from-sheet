#!/data/data/com.termux/files/usr/bin/bash
# Add a number to the never-text list (someone replied stop / remove me / asked not to be contacted).
. "$(dirname "$0")/common.sh"
echo "Type the phone number of the person who asked not to be texted."
read -r -p "Number: " NUM
NUM="$(printf '%s' "$NUM" | tr -cd '0-9+')"
[ ${#NUM} -ge 10 ] || { echo "That doesn't look like a full phone number. Nothing saved."; pause; exit 1; }
printf '%s\n' "$NUM" >> do_not_text.csv
echo "Saved. $NUM will never be texted by this tool."
echo "If a text is running, tap 'Text 4 Stop', then 'Text 2 Start' so it picks up the change."
pause
