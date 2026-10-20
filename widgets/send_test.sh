#!/data/data/com.termux/files/usr/bin/bash
# Sends ONE text, the first person's message, to your OWN number so you can see exactly what people get.
. "$(dirname "$0")/common.sh"; need_ready
read -r -p "Your own phone number: " ME
python3 android/send_slow.py list.csv --message-file message.txt --campaign "$CAMPAIGN" $FLAGS --test-to "$ME"
echo; pause
