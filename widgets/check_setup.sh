#!/data/data/com.termux/files/usr/bin/bash
# Checks that everything needed is installed and allowed. Sends nothing.
TOOL="${TEXTTOOL_DIR:-$HOME/text-tool}"
ok()  { echo "OK       $1"; }
bad() { echo "MISSING  $1"; PROBLEMS=1; }
PROBLEMS=0
[ -d "$TOOL" ] && ok "tool folder" || bad "tool folder ($TOOL). Redo the setup steps."
command -v python3 >/dev/null && ok "python3" || bad "python3 (run: pkg install python)"
command -v tmux >/dev/null && ok "tmux" || bad "tmux (run: pkg install tmux)"
command -v termux-sms-send >/dev/null && ok "Termux:API commands" || bad "Termux:API (install the Termux:API app, then: pkg install termux-api)"
if command -v termux-sms-list >/dev/null; then
  timeout 15 termux-sms-list -l 1 >/dev/null 2>&1 && ok "SMS permission" || bad "SMS permission (Settings > Apps > Termux:API > Permissions > SMS > Allow)"
fi
[ -d "$HOME/storage/downloads" ] && ok "Downloads access" || bad "Downloads access (run: termux-setup-storage, tap Allow)"
[ -f "$HOME/storage/downloads/list.csv" ] || [ -f "$TOOL/list.csv" ] && ok "list.csv found" || bad "list.csv (save your list in Downloads named list.csv)"
[ -f "$TOOL/message.txt" ] && ok "message saved" || bad "message (tap Text-6-Change-message)"
echo
[ "$PROBLEMS" = 0 ] && echo "All good. Tap Text-1-Preview next." || echo "Fix the MISSING items above, then tap this button again."
read -r -p "Press Enter to close" _ || true
exit "$PROBLEMS"
