#!/data/data/com.termux/files/usr/bin/bash
# Text your message WITH a picture. Save the picture in Downloads as picture.jpg (or .png / .gif / .vcf).
# For each person, Messages opens with everything filled in; you press Send, come back, press Enter.
. "$(dirname "$0")/common.sh"; need_ready
PIC=""
for f in "$HOME"/storage/downloads/picture.{jpg,jpeg,png,gif,webp,heic,vcf,pdf}; do [ -f "$f" ] && { PIC="$f"; break; }; done
[ -n "$PIC" ] || { echo "No picture found. Save it in Downloads named picture.jpg (or picture.png), then tap again."; pause; exit 1; }
python3 android/send_picture.py list.csv --message-file message.txt --campaign "$CAMPAIGN-picture" $FLAGS --attach "$PIC"
echo; pause
