#!/data/data/com.termux/files/usr/bin/bash
# One-time (and again whenever you change the birthday message): sets the message, asks for your
# one-time approval, and turns on the daily check. Your list needs a Birthday column (like 03/14).
. "$(dirname "$0")/common.sh"
[ -f list.csv ] || { echo "No list yet. Tap Text-0-Choose-list first (it needs Phone and Birthday columns)."; pause; exit 1; }
echo "Birthday message. Put {first_name} where the name goes. Keep it a simple greeting."
echo "Example: Happy birthday, {first_name}! Hope it's a great one. - Jordan"
read -r -p "Message: " MSG
[ -n "$MSG" ] || { echo "No message entered. Nothing changed."; pause; exit 1; }
printf '%s\n' "$MSG" > birthday_message.txt
echo
python3 android/send_slow.py list.csv --message-file birthday_message.txt --campaign birthday --birthdays-today --approve-auto $FLAGS || { echo; echo "Not turned on."; pause; exit 1; }
# Daily timer: every hour from 8:05 to 4:05. Re-runs are harmless (nobody is texted twice in a year),
# and it catches a day when the phone was asleep at 8am.
ENTRY="5 8-16 * * * cd $TOOL && bash widgets/birthday_run.sh"
command -v crontab >/dev/null || { pkg install -y cronie termux-services; }
( crontab -l 2>/dev/null | grep -v "widgets/birthday_run.sh"; echo "$ENTRY" ) | crontab -
command -v sv-enable >/dev/null && sv-enable crond >/dev/null 2>&1
echo
echo "Automatic birthday texts are ON."
echo "If this is the first time: close Termux completely and open it once so the timer service starts."
echo "Pause them any time with Text-5-Stop. Turn back on by running this button again."
echo "See what happened: open birthday_log.txt in the text-tool folder, or tap Text-4-Status."
pause
