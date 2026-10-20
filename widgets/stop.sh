#!/data/data/com.termux/files/usr/bin/bash
. "$(dirname "$0")/common.sh"
touch STOP
echo "Stop requested. It will stop after the current text (within about a minute)."
echo "To start again later, tap 'Text 2 Start'. It will not text anyone twice."
pause
