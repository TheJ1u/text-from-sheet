# Suggestions for future improvements

1. **Generate and sign the real `.shortcut`** on a Mac with `shortcuts sign` (or hand-build once, then export), and add a device test script. That is the biggest gap today.
2. **Pre-clean on Mac/phone**: a tiny hosted-nowhere workflow (Python on Mac, or Pythonista/a-Shell on iPhone) that runs `sms_prep.py check` and hands the Shortcut a ready `queue.csv`. Moves all parsing/validation out of Shortcuts and removes the fixed-column limitation.
3. **Better delivery tracking**: for real delivery receipts you need an SMS API (Twilio etc.) with webhooks. That costs money, needs 10DLC registration for business traffic, and changes the compliance picture; only worth it at volume.
4. **Consent capture**: keep consent in a proper source (CRM or form) and export it, rather than a spreadsheet column.
5. **Opt-out handling**: a small Shortcut/Automation to add a number to `suppression_list.csv` from a "STOP" reply in one tap.
6. **Calendar integration**: pull appointment reminders from Calendar instead of typing dates in the sheet.
7. **Per-contact send windows** (e.g. no texts before 8am or after 9pm local) as a warning in the review screen.
8. **CI**: run the unit tests on every change (GitHub Actions is free for this).
9. **Learning angle** (your Information Systems path): this is a small data-pipeline pattern: *ingest, validate, transform, human-in-the-loop approval, audit log*. The same structure scales to any ops workflow and is good portfolio material.

## Birthday automation: still unverified
Built and tested with a fake clock and fake phone commands. Not yet confirmed on a real phone: that `cron` runs inside Termux after the one-time restart, that the phone stays awake enough, and that Android lets Termux send while the screen is off. Check `birthday_log.txt` after the first real birthday.

## Picture mode: still unverified
Built and tested with fakes. On a real phone, confirm: the Messages app opens with the picture attached, whether it fills in the number (if not, paste), and that the text comes through with the picture (some apps drop one of the two).
