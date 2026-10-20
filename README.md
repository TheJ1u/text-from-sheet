# Text From Sheet

A small, safety-first toolkit for texting a list of people from a phone's **own number**: upload a
spreadsheet (CSV), write one message with merge fields like `{first_name}`, and send it either one
tap at a time (web page) or paced automatically in the background (Android/Termux).

**The problem:** non-technical people with a contact list and a personal phone have no safe, simple way
to send personalized texts. Bulk-SMS platforms need accounts, fees and carrier registration; copy-pasting
400 messages by hand is error-prone. This tool keeps the data on the phone and puts guardrails around the
risky parts (bad numbers, duplicates, people who opted out, sensitive data, sending at night).

## What's in the box
| Piece | What it does | Status |
|---|---|---|
| `android/send_slow.py` | Paced background sender for Android (Termux). One text ~every 65 s, only 8am-6pm, one up-front approval, resumable, stop switch, live notification, `--status`, `--dry-run` preview, log | Built; unit-tested with a fake sender |
| `web/index.html` | Single-file web app (no server): upload CSV, merge fields, review each person, opens the SMS app pre-filled | Built; logic + flow tested in a simulated browser |
| `android/scan_replies.py` | Reads received texts, finds "stop / remove me" replies from people on your list, adds them to the never-text list after a typed YES | Built; tested with fake data |
| `tools/sms_prep.py` | Rules engine: phone normalization (E.164), consent / opt-out / suppression, dedupe, sensitive-data blocking, templates, resume | Built; 36 tests |
| `widgets/` | One-tap home-screen buttons for Android (Termux:Widget): Check setup, Preview, Test-to-me, Start, Status, Stop, Change message, Do-not-text, Check replies | Built; script-tested in a temp folder, not on a phone |
| `docs/BUILD_SHORTCUT.md` | Exact build spec for an iPhone Shortcut version | Spec only; not built or tested on a device |

**Honest status:** all logic is covered by automated tests (91 Python + 13 JavaScript). Nothing has yet been
tested on a physical phone; do the small real-number test in `docs/PHONE_SETUP.md` first.

## How the Android sender works
```
CSV ──► validate ──► preview ──► YES / SEND ──► send 1 text ──► log ──► wait 65 s ──► repeat
        (phone, dupes,  (--dry-run,   (typed          (termux-sms-send)   (every text)   (8am-6pm only;
         opt-out, no     nothing        approval,                                         pauses overnight,
         sensitive)      sent)          once)                                             resumes itself)
```
Safety rules are in code, not optional: 60 s minimum between texts, send window, typed approval (no
`--yes` flag), stops after 3 failures in a row, Stop file, never re-texts a number already submitted,
never invents a missing name, and the log records "submitted," never "delivered."

## Quick start
```
python3 -m unittest discover -s tests                     # 91 tests
python3 android/send_slow.py data/sample_contacts.csv --message "Hi {first_name}!" \
    --campaign demo --dry-run                             # preview only, sends nothing
```
Phone setup (non-technical, copy-paste): `docs/PHONE_SETUP.md`. Details: `docs/ANDROID_TERMUX.md`,
`docs/ANDROID_WEB_APP.md`, `docs/IOS_LIMITATIONS.md`, `docs/COMPLIANCE_NOTES.md`, `docs/ROADMAP.md`.

## Responsible use
Only text people who know you and expect to hear from you, and honor anyone who says stop. This tool does
not hide activity from the phone or carrier, and it is not legal advice. See `docs/COMPLIANCE_NOTES.md`.

## What I learned / design decisions
- Parsing and rules live in tested Python; thin UIs (web page, Termux script) sit on top.
- A web page cannot silently send SMS (by design), so the web version is human-in-the-loop and the
  automated version is a separate, explicitly approved, rate-limited tool.
- Privacy by architecture: no server, no accounts, contact data never leaves the phone.

License: MIT.
