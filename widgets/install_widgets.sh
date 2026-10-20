#!/data/data/com.termux/files/usr/bin/bash
# One-time: creates the home-screen buttons (needs the Termux:Widget app).
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${SHORTCUTS_DIR:-$HOME/.shortcuts}"
mkdir -p "$DEST"
make_stub() {  # name, script
  printf '#!/data/data/com.termux/files/usr/bin/bash\nexec bash "%s/%s"\n' "$SRC" "$2" > "$DEST/$1"
  chmod 700 "$DEST/$1"
}
make_stub "Text-1-Preview" preview.sh
make_stub "Text-2-Start" start.sh
make_stub "Text-3-Status" status.sh
make_stub "Text-4-Stop" stop.sh
make_stub "Text-5-Change-message" set_message.sh
make_stub "Text-6-Do-not-text" do_not_text.sh
echo "Buttons created: Text-1-Preview, Text-2-Start, Text-3-Status, Text-4-Stop, Text-5-Change-message, Text-6-Do-not-text"
echo "Now: long-press your home screen > Widgets > Termux:Widget > add the shortcut list."
[ -f "$SRC/../message.txt" ] || { echo; echo "Let's set your message now."; bash "$SRC/set_message.sh"; }
