# Slow sender for Android (Termux): setup and use

Sends one text about every minute from the phone's own number, only between 8am and 6pm (phone-local time), in the background, with one up-front approval. No per-run limit: 400 texts fit in one day's window. Script: `android/send_slow.py`. **Tested with a fake sender (automated tests). Not yet tested on a
real phone; do the "first test" below before the real list.**

## One-time setup (about 15 minutes)
1. **Install Termux and Termux:API from F-Droid** (f-droid.org). Both apps must come from the same source or they won't talk to each other.
2. Open **Termux** and run:
   ```
   pkg update && pkg install python termux-api git tmux
   termux-setup-storage
   ```
3. **Give SMS permission:** Android Settings → Apps → **Termux:API** → Permissions → **SMS** → Allow. (On some phones also allow Phone.)
4. **Copy the project folder** (`jenkins-sms-shortcut`, includes `android/` and `tools/`) onto the phone, e.g. into Downloads, then in Termux:
   ```
   cp -r ~/storage/downloads/jenkins-sms-shortcut ~/ && cd ~/jenkins-sms-shortcut
   ```
5. **Keep it alive in the background** (see the section below).

## First test (do this before 400 people)
Make `test.csv` with 2 rows: one is **your own number**, one is a family member who knows to expect it.
```
First Name,Phone
Dad,+1801XXXXXXX
```
```
python3 android/send_slow.py test.csv --message "Hi {first_name}, test text." --campaign test --dry-run
python3 android/send_slow.py test.csv --message "Hi {first_name}, test text." --campaign test
```
Confirm the text arrives from the phone's number and shows in its Messages app.

## The real list
CSV needs a **Phone** column. Optional: First Name, Last Name, any other columns for `{fields}`. Optional columns the tool honors: `Opt Out` (yes = skip), `Consent` (if the column exists, only "yes" rows are texted).
Export from Excel as **CSV (UTF-8)**; format phone cells as Text first.

1. Preview (sends nothing):
   ```
   python3 android/send_slow.py list.csv --message-file msg.txt --campaign fall-dinner --dry-run
   ```
   Shows who's ready, who's skipped and why, the first 3 messages, and how long it will take.
2. Run it inside tmux so it keeps going if the Termux window closes:
   ```
   tmux new -s texts
   python3 android/send_slow.py list.csv --message-file msg.txt --campaign fall-dinner
   ```
   Type `YES` (permission) then `SEND`. Detach with **Ctrl-b then d**. Reattach: `tmux attach -t texts`.
3. It sends **the whole list in one run**, one text every 65 seconds, **only 8am-6pm phone time**. Outside those hours it waits and picks up the next morning by itself (400 texts is about 7 hours, so it fits in one day if started by about 10am). Change hours with `--window-start 9 --window-end 17`. If you stop it, run the same command again to continue. It never re-texts a number already marked submitted.

## Can it run in the background? Yes, with these steps (phone makers vary)
- Keep the phone **plugged in**. The script requests a wake lock itself (`termux-wake-lock`).
- Settings → Apps → **Termux** → Battery → **Unrestricted** (also keep the phone plugged in overnight if it will wait for morning; Samsung: remove Termux from "Sleeping apps"/"Deep sleeping apps"; Xiaomi/Oppo/OnePlus: allow autostart and background activity).
- Don't swipe Termux away from recent apps; leave its notification showing.
- Check on it after a few minutes to confirm texts are still going out before leaving it for hours. Some phones still kill background apps, and then you resume by running the command again.

## Stop, resume, log
- **Stop:** Ctrl-C, or in another Termux session run `touch STOP` in the project folder. It stops after the current text.
- **Resume:** run the same command again.
- **Log:** `send_log.csv` (timestamp, number, name, `submitted` or `failed`, message). `submitted` means the phone accepted it; **delivery is not confirmed**. Check Messages for "Not delivered".
- **Failures:** after 3 in a row it stops (usually missing SMS permission or no signal).

## Built-in limits (on purpose)
- 60-second minimum between texts. This follows the pace Android and carriers tolerate (Android typically prompts after about 30 texts in 30 minutes, from memory, so verify on the phone). If Android shows a "large number of messages" prompt, tap Allow or stop and resume later.
- Sends only inside the 8am-6pm window (it uses the phone's local time, not the recipients'). No per-run cap unless you add `--max-per-run N`.
- No "yes to everything" flag: it always asks for YES and SEND after showing the preview.
- Nothing here hides the activity from the phone or carrier. A personal number sending many similar texts can still be blocked by a carrier; keep the list to people who know the sender and expect to hear from him, and honor anyone who says stop (add to `--suppression` file or mark `Opt Out`).
- Dual SIM: add `--sim 1` or `--sim 2`.
- The send window uses the **phone's** time unless your list has a `Timezone` column (for example `America/Los_Angeles`). With that column, each person is texted only during 8am-6pm in their own time zone; people outside it are skipped for now and picked up later. An unknown time zone name holds that person back.
- `--require-consent` refuses everyone unless a Consent column says yes (and refuses a list with no such column). Recommended for any marketing-type texts.
- `--test-to YOUR_NUMBER` sends one test text to your own phone, then exits.
- Picture mode: `python3 android/send_picture.py list.csv --message-file message.txt --campaign flyer --attach ~/storage/downloads/picture.jpg`. It opens Messages with the number, text and picture for one person at a time; you press Send. It uses an Android share request (`am start ... SEND`) and copies the number in case your Messages app ignores the pre-filled number. Whether Google Messages and Samsung Messages fill in the number this way is **not yet tested on a phone**.
- Birthday mode: `--birthdays-today` keeps only people whose `Birthday` column is today and adds the year to the batch name (so nobody gets two in a year). Feb 29 birthdays are texted on Feb 28 in non-leap years. `--approve-auto` records a one-time typed approval of the exact message, hours and consent rule; `--auto` (used by the daily timer) refuses to send unless that approval still matches, skips if STOP exists, skips if outside the hours (a birthday text a day late is not sent), and uses a lock so two runs never overlap. `--auto` only works together with `--birthdays-today`.
- `python3 android/scan_replies.py list.csv` finds people who texted back stop and adds them to `do_not_text.csv`.
- A `--suppression` file that doesn't exist is an error (not silently ignored), so a typo can't skip your do-not-text list.
- Curly quotes, emoji and accents make a text count 70 characters per piece instead of 160. The preview warns you.
