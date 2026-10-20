# iOS limitations (what this design works around, and what it cannot do)

Items marked **(verify)** are things I believe but did not test on a device.

1. **No guaranteed silent bulk sending, by design.** Apple's Shortcuts "Send Message" action is meant to go through Messages. Depending on iOS version, settings and how a shortcut is launched, iOS may or may not show a confirmation. **(verify on your iOS version.)** This project deliberately keeps *Show Compose Sheet* ON so you tap Send for every recipient. That also satisfies "explicit approval per recipient." No private APIs, no jailbreak, no workarounds.
2. **No delivery receipts.** Shortcuts cannot read delivered/read/failed status from Messages. The log therefore records the *action outcome you confirm* (`sent_action_completed`) and always writes `delivery_confirmed = unknown`. Check Messages for "Delivered"/red "Not Delivered".
3. **Compose-sheet cancel behavior is unclear. (verify)** Whether a cancelled sheet stops the shortcut or continues varies. Step 34's "Did you tap Send?" menu captures the truth; an interrupted run leaves the recipient in `approved_keys.txt` so the next run holds it for manual check instead of re-sending.
4. **iMessage vs SMS.** Messages decides per recipient. Green-bubble SMS needs cell service and may use your carrier plan. Group/MMS behavior is not covered.
5. **Native CSV parsing is simple.** Shortcuts has no CSV parser. The shortcut splits on commas and uses fixed column order, so commas inside fields break a row (the row is rejected, not mis-sent). Excel `.xlsx` cannot be read natively: export CSV (Numbers/Excel export, or `tools/xlsx_to_csv.py`).
6. **Excel damages phone numbers.** It drops `+`, strips leading zeros, and turns long numbers into `1.80155E+10`. The shortcut rejects scientific notation and numbers with no country code rather than guessing. Format the phone column as **Text** before typing numbers.
7. **No loops with exit conditions or functions.** Shortcuts has *Repeat* and *Repeat with Each* only; the edit flow uses a fixed 5-pass repeat. Very long lists can be slow; split large files.
8. **No secure secret store.** See `AI_PROVIDERS.md`.
9. **iCloud sync lag.** If you run on iPhone and iPad, `send_log.csv` / `processed_keys.txt` may not have synced. Use one device per campaign, or wait for sync before resuming.
10. **Log durability.** The log is a plain file you can edit or delete. It is a working record, not tamper-proof evidence.
11. **Siri / Share Sheet.** Both start the same shortcut; Siri has no spreadsheet to hand it, so it falls back to *Select File*. Running from a lock screen may require unlocking.
12. **Background/automation.** Do not attach this to a personal automation or schedule it. It is intentionally interactive.
