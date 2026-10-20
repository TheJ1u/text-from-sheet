#!/data/data/com.termux/files/usr/bin/bash
. "$(dirname "$0")/common.sh"
echo "Type your message. Put {first_name} where each person's first name should go"
echo "(only if your list has a First Name column)."
read -r -p "Message: " MSG
[ -n "$MSG" ] || { echo "No message entered. Nothing changed."; pause; exit 1; }
printf '%s\n' "$MSG" > message.txt
read -r -p "Name for this batch, letters/numbers only (e.g. fall-dinner) [mytexts]: " C
C="$(printf '%s' "${C:-mytexts}" | tr -c 'A-Za-z0-9_-' '-')"
printf '%s\n' "$C" > campaign.txt
read -r -p "Must every person have 'yes' in a Consent column? (y/N): " RC
case "$RC" in [yY]*) echo yes > require_consent.txt ;; *) rm -f require_consent.txt ;; esac
echo; echo "Saved. Message: $MSG"; echo "Batch name: $C"
echo "(Use a NEW batch name for a new list, or people already texted under the old name will be skipped.)"
echo; pause
