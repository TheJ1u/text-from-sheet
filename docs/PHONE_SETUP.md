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

## Optional: one-tap buttons on the home screen
1. Install **Termux:Widget** (same steps as Part 1): https://f-droid.org/packages/com.termux.widget/
2. In Termux, copy this box once. It asks for your message and adds the buttons:
```
bash ~/text-tool/widgets/install_widgets.sh
```
3. Long-press the home screen > **Widgets** > **Termux:Widget** > add it. You get nine buttons:

| Button | What it does |
|---|---|
| Text-0-Check-setup | Checks everything is installed and allowed. Sends nothing. |
| Text-1-Preview | Shows who will get what. Sends nothing. |
| Text-2-Send-test-to-me | Sends ONE text, exactly as people will get it, to your own number. |
| Text-3-Start | Starts the real send. Type YES, then SEND. |
| Text-4-Status | Shows how many are done. |
| Text-5-Stop | Stops after the current text. |
| Text-6-Change-message | Changes the message (and whether a Consent column is required). |
| Text-7-Do-not-text | Adds a number that must never be texted. |
| Text-8-Check-replies | Finds people who texted back stop / remove me and offers to add them to the never-text list. |
| Text-9-Birthday-setup | Sets up automatic birthday texts (see below). |
| Text-P-Send-with-picture | Sends your message with a picture (see below). |

Order: 0, then 1, then 2, then 3. Run 8 now and then, and always before a new batch.

## Optional: send a picture or file with your message
1. Save the picture in **Downloads** named `picture.jpg` (or `picture.png`).
2. Tap **Text-1-Preview** as usual, then **Text-P-Send-with-picture** and type `YES`.
3. For each person, Messages opens with the number, the message and the picture. Press **Send**, come back to Termux, press **Enter** for the next person (`s` skips, `q` stops).

If the **To** field is empty, long-press it and **Paste**: the number is already copied. Picture texts can't go out automatically in the background (Android doesn't allow it), so this mode is for smaller lists. For hundreds of people, put a link to the picture in a normal text instead. PDFs often don't go through as texts; use a link for those.

## Optional: automatic birthday texts
1. Add a **Birthday** column to `list.csv` (like `03/14` or `1948-03-14`). Month comes first.
2. Tap **Text-9-Birthday-setup**. Type the birthday message, then type `YES` and `SEND` once. That is your approval for that exact message.
3. Close Termux completely and open it once, so the daily timer starts.

After that, once a day between 8am and 6pm, the phone texts only the people whose birthday is today, one text at a time, once per year each. If you change the message, automatic texts stop until you tap the button and approve again. **Text-5-Stop** pauses them. Keep it a simple greeting, keep the phone charged and set to Unrestricted battery, and look at `birthday_log.txt` after the first birthday to confirm it worked.

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
