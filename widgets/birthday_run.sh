#!/data/data/com.termux/files/usr/bin/bash
# Run by the daily timer (not a button). Texts today's birthdays, only if the saved approval still matches.
TOOL="${TEXTTOOL_DIR:-$HOME/text-tool}"
cd "$TOOL" || exit 1
[ -f "$HOME/storage/downloads/list.csv" ] && cp -u "$HOME/storage/downloads/list.csv" "$TOOL/list.csv"
[ -f do_not_text.csv ] || echo "Phone" > do_not_text.csv
FLAGS="--suppression do_not_text.csv"
[ -f require_consent.txt ] && FLAGS="$FLAGS --require-consent"
{
  echo "--- $(date '+%Y-%m-%d %H:%M')"
  python3 android/send_slow.py list.csv --message-file birthday_message.txt --campaign birthday \
    --birthdays-today --auto $FLAGS
} >> birthday_log.txt 2>&1
