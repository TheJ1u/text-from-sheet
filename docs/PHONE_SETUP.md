# Phone setup (copy-paste version)

## Part 1: Download (on the phone)
1. **Termux** (tap "Download APK"; the stable one is fine): https://f-droid.org/packages/com.termux/
2. **Termux:API** (same): https://f-droid.org/packages/com.termux.api/

   If the phone asks to "allow installs from this browser," say yes, then open each file to install.
3. Save your contact list in **Downloads** and name it `list.csv`. It needs a column named **Phone**.

## Part 2: Settings (no typing)
- Settings > Apps > **Termux:API** > Permissions > **SMS** > Allow
- Settings > Apps > **Termux** > Battery > **Unrestricted**

## Part 3: Open Termux and copy each box, one at a time (press Enter after each)
```
pkg update -y && pkg install -y python termux-api git tmux
```
Tap **Allow** when it asks:
```
termux-setup-storage
```
```
git clone https://github.com/TheJ1u/text-from-sheet ~/text-tool
```
```
cp ~/storage/downloads/list.csv ~/text-tool/ && cd ~/text-tool
```

## Part 4: Preview (sends NOTHING)
Change the words in quotes to your message first.
```
python3 android/send_slow.py list.csv --message "Hi {first_name}, your message here" --campaign mytexts --dry-run
```
(`{first_name}` needs a First Name column in your list. If you don't have one, remove it from the message.)

## Part 5: Send
```
tmux new -s texts
```
Same message as the preview, without `--dry-run`:
```
python3 android/send_slow.py list.csv --message "Hi {first_name}, your message here" --campaign mytexts
```
It asks two questions: type **YES**, Enter, then **SEND**, Enter. Then press **Ctrl and b together**, let go, press **d**. It keeps running in the background. Keep the phone plugged in.

## Check progress (also shown in the phone's notification bar)
```
cd ~/text-tool && python3 android/send_slow.py list.csv --message "Hi" --campaign mytexts --status
```

## Stop
```
cd ~/text-tool && touch STOP
```

## Update the tool (only when told to)
```
cd ~/text-tool && git pull
```

## Continue later
Do Part 5 again. It will not text anyone twice.

## The rules
One text about every minute from your own number. It only sends 8am to 6pm, waits overnight, and continues in the morning. 400 people takes about 7 hours.
