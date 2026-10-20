#!/data/data/com.termux/files/usr/bin/bash
# One-time: creates the home-screen buttons (needs the Termux:Widget app).
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${SHORTCUTS_DIR:-$HOME/.shortcuts}"
mkdir -p "$DEST"
make_stub() {  # name, script
  printf '#!/data/data/com.termux/files/usr/bin/bash\nexec bash "%s/%s"\n' "$SRC" "$2" > "$DEST/$1"
  chmod 700 "$DEST/$1"
}
make_stub "Text-0-Check-setup" check_setup.sh
make_stub "Text-1-Preview" preview.sh
make_stub "Text-2-Send-test-to-me" send_test.sh
make_stub "Text-3-Start" start.sh
make_stub "Text-4-Status" status.sh
make_stub "Text-5-Stop" stop.sh
make_stub "Text-6-Change-message" set_message.sh
make_stub "Text-7-Do-not-text" do_not_text.sh
make_stub "Text-8-Check-replies" check_replies.sh
make_stub "Text-9-Birthday-setup" birthday_setup.sh
make_stub "Text-P-Send-with-picture" picture_send.sh
echo "Buttons created (0 to 9, plus P). Start with Text-0-Check-setup."
echo "Now: long-press your home screen > Widgets > Termux:Widget > add the shortcut list."
[ -f "$SRC/../message.txt" ] || { echo; echo "Let's set your message now."; bash "$SRC/set_message.sh"; }
