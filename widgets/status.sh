#!/data/data/com.termux/files/usr/bin/bash
. "$(dirname "$0")/common.sh"; need_ready
python3 android/send_slow.py list.csv --message-file message.txt --campaign "$CAMPAIGN" --suppression do_not_text.csv --status
echo; pause
