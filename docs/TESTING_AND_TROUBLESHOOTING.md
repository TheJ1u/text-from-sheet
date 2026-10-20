# Testing and troubleshooting

## A. Automated tests (done, run on this repo)
```
python3 -m unittest discover -s tests -v      # 132 tests, all passing
python3 tools/sms_prep.py check data/sample_contacts.csv \
  --suppression data/suppression_list.csv --campaign demo --out out
```
Expected from the sample file: **5 ready, 2 flagged for review (Chloe, Kara), 10 rejected**, "Nothing was sent."
Covered: phone formats and damage, consent/opt-out/suppression, duplicates, sensitive-data blocking,
review flags, resume rules, AI payload minimization and output guard, XLSX input, no network/send code,
no API keys in the repo.

## B. On-device acceptance tests (you must run these; I could not)
Use `data/sample_contacts.csv` copied to iCloud Drive. Replace one fictional row's phone with **your own number**; leave Compose Sheet ON.

| # | Do | Expected |
|---|---|---|
| 1 | Run from Share Sheet on the CSV | Starts, no file picker |
| 2 | Run from Home Screen / say "Text From Sheet" | File picker appears |
| 3 | Campaign `test1`, Template mode | Review screen for Ava first, then Ben, Chloe (⚠ review), Daniel, Kara (⚠ review) |
| 4 | Approve Ava, tap Send in Messages, answer "Yes" | Log row `approved` then `sent_action_completed`, delivery `unknown` |
| 5 | Skip Ben | Log `skipped` |
| 6 | Edit Daniel's text to include `123-45-6789` | Blocked, not sendable |
| 7 | Approve Kara, cancel in Messages, answer "No, I canceled" | `canceled`, retryable |
| 8 | Cancel run at Chloe | Summary shows; nothing else processed |
| 9 | Run again with campaign `test1` | Ava and Ben not offered again; Kara and Chloe (retryable) are |
| 10 | Force-quit during Messages after Approve | Next run holds that recipient for manual check |
| 11 | Look for a "send all"/auto-approve path | There must be none |
| 12 | Rejected rows (Eva, Frank, Grace, dup Ava, Henry, Isla, Jack, Liam, Mia, Wright) | Never shown for sending; logged `blocked` with reason |
| 13 | AI mode with a fictional name | Draft only changes wording; numbers/dates unchanged; flagged `ai_edited` |

## C. Troubleshooting
| Symptom | Cause / fix |
|---|---|
| "Columns must match…" | Header differs from `sample_contacts.csv`. Same names, same order, 16 columns. |
| Every row `malformed_row_check_commas` | Commas inside fields, or the file is `;`-separated. Remove commas or re-export CSV (UTF-8). |
| Phones rejected `phone_needs_country_code` | Not 10-digit US and no `+`. Write international numbers as `+44…`. |
| `phone_scientific_notation` | Excel damaged the cell. Set the column to Text and retype, or fix at the source. |
| Rows missing / "no consent" | `Consent` must be Yes/Y/True/1/Opt in/Granted. Blank is never consent. |
| Nothing sends | Compose Sheet is intentional; tap Send in Messages. Check Settings > Shortcuts > allow Messages. |
| Log not updating | `send_log.csv` must exist in Shortcuts/TextFromSheet with the header row; check iCloud sync. |
| Resumed run repeats someone | You switched devices before iCloud synced `processed_keys.txt`; check Messages > Sent. |
| AI step fails | Wrong key/model ID, no network, or spend limit; shortcut falls back to the template draft. |
| `.xlsx` won't open | Convert: `python3 tools/xlsx_to_csv.py in.xlsx out.csv`, or Numbers/Excel export. |
