#!/data/data/com.termux/files/usr/bin/bash
. "$(dirname "$0")/common.sh"; need_ready
# Runs inside tmux so it keeps going if you close this window or leave Termux.
# If it is already running, this reattaches to it so you can watch.
command -v tmux >/dev/null || { echo "tmux missing. Run: pkg install tmux"; pause; exit 1; }
tmux new-session -A -s texts "python3 android/send_slow.py list.csv --message-file message.txt --campaign '$CAMPAIGN' --suppression do_not_text.csv; echo; read -r -p 'Press Enter to close' _"
