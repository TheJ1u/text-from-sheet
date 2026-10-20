#!/data/data/com.termux/files/usr/bin/bash
. "$(dirname "$0")/common.sh"; need_ready
echo "PREVIEW ONLY: nothing is sent."
python3 android/send_slow.py list.csv --message-file message.txt --campaign "$CAMPAIGN" $FLAGS --dry-run
echo; pause
