# Build the "Text From Sheet" Shortcut (action-by-action)

**Status: this is a build specification, not a tested shortcut.** I could not generate a signed
`.shortcut` file (that needs macOS `shortcuts sign` and a device), and I have not run any of this
on an iPhone. The *rules* it implements are tested in `tools/sms_prep.py` (36 passing tests). Build it,
then run `docs/TESTING_AND_TROUBLESHOOTING.md` on your phone before using it for real people.
Action names below match the Shortcuts app as I know it; menus can differ slightly by iOS version.

## 0. Folder and files (iCloud Drive > Shortcuts > TextFromSheet)

Create the folder in the Files app, then add:

| File | Content |
|---|---|
| `send_log.csv` | Header only: `timestamp,session_id,recipient_key,phone,name,template,campaign,status,delivery_confirmed,note` (or `python3 tools/sms_prep.py init-log send_log.csv`) |
| `processed_keys.txt` | Empty. One recipient_key per line once its outcome is final (`sent_action_completed`, `skipped`, `blocked`). |
| `approved_keys.txt` | Empty. One key per line when approved; used to catch "approved but outcome unknown" after a crash. |
| `suppression_list.csv` | Copy of `data/suppression_list.csv`. Put every opted-out number here in `+1XXXXXXXXXX` form. |

`recipient_key` = `campaign|template|+E164phone` (same as the Python tool).

## 1. Shortcut settings (ⓘ / Details)

- Name: `Text From Sheet`
- Show in Share Sheet: ON, accepts **Files** and **Text**. If asked "if there's no input": **Ask For** (or fall back to *Select File*, step 1.1).
- Pin in Home Screen: ON (add to Home Screen from the share/“…” menu).
- Siri: the shortcut name is the phrase: "Text From Sheet".

## 2. Actions in order

### Phase A: constants
1. **Dictionary** `Config`: `business_name` = Jenkins Insurance and Retirement, `agent_name` = Jordan Jenkins. *(No API keys here, ever. See `AI_PROVIDERS.md`.)*
2. **Format Date** (Current Date, Custom `yyyyMMdd-HHmmss`) → **Set Variable** `SessionID`.
3. **Ask for Input** (Text) "Campaign ID (e.g. fall-2026-workshop)" → **Set Variable** `Campaign`.
4. **Choose from Menu** "Message source": `Template (no AI)` / `Claude` / `ChatGPT` → **Set Variable** `Mode`. (Default to the first.)
5. **Get File** (Shortcuts/TextFromSheet/processed_keys.txt) → **Get Text from Input** → **Set Variable** `Processed`. Repeat for `approved_keys.txt` → `ApprovedOnly`, `suppression_list.csv` → `Suppress`.
6. **List** (empty) → **Set Variable** `SeenPhones`. **Number** 0 → `CountSent`, `CountSkipped`, `CountRejected`, `CountCanceled`, `CountFailed`.

### Phase B: import
7. **If** *Shortcut Input* **has any value** → **Set Variable** `File` = Shortcut Input. **Otherwise** → **Select File** → `File`. **End If**.
8. **Get Text from Input** (File) → **Split Text** (Separator **New Lines**) → **Set Variable** `Lines`.
9. **Get Item from List** (Lines, **First Item**) → `Header`. Check it equals the template header: **If** `Header` **does not contain** `First Name,Last Name,Phone Number,Message,Notes,Status,Consent,Consent Date,Consent Source,Opt Out,Message Type,Template,Appointment Date,Appointment Time,Event Name,Event Date` → **Show Alert** "Columns must match sample_contacts.csv exactly (same order)." → **Stop This Shortcut**.
10. **Get Items from List** (Lines, **Items in Range** 2 to last) → **Repeat with Each** `Line`. *(Everything below is inside this loop.)*

> **Native-CSV limits:** the Shortcut splits on commas, so fields with commas break. Rows with too many fields are rejected (step 12). Column order is fixed (the Python tool matches by header name; the Shortcut matches by position). Export Excel as CSV (UTF-8) or use `tools/xlsx_to_csv.py`.

### Phase C: per-row gate (any failure → log `blocked` + reason, `CountRejected += 1`, skip to next row)
11. **If** `Line` **has no value**/is empty → skip row. Else **Split Text** (`Line`, Custom separator `,`) → `F`.
12. **Count** (F) → **If** not **equal to** 16 → reject `malformed_row_check_commas`.
13. **Get Item from List** index 1..16 → **Set Variable**: `First`(1) `Last`(2) `PhoneRaw`(3) `MsgCol`(4) `Notes`(5) `Status`(6) `Consent`(7) `ConsentDate`(8) `ConsentSrc`(9) `OptOut`(10) `MType`(11) `Tpl`(12) `ApptDate`(13) `ApptTime`(14) `EvName`(15) `EvDate`(16). Trim each (**Replace Text**, regex on, `^\s+|\s+$` → empty).
14. **Phone.** **Match Text** `[A-Za-z]` on `PhoneRaw`: if any match → reject `phone_has_letters_or_sci_notation_or_ext`. **Replace Text** (regex on) `[^0-9+]` → *(empty)* on `PhoneRaw` → `P`.
    - **Match Text** `^\+[1-9][0-9]{7,14}$` on `P`: match → `Phone` = `P` (international, kept as is).
    - Else **Match Text** `^1?[2-9][0-9]{2}[2-9][0-9]{6}$`: match → **Replace Text** (regex) `^1?` → `+1` → `Phone`.
    - Else reject `phone_needs_country_code_or_invalid`.
    - (Also for `+1…` numbers, require `^\+1[2-9][0-9]{2}[2-9][0-9]{6}$`.)
15. **Required fields:** `First` empty → reject `missing_first_name`.
16. **Consent.** **Change Case** (Consent → lowercase) → **Match Text** `^(yes|y|true|1|opted in|opt in|opt-in|granted)$`. No match → reject `no_affirmative_consent`. **Never** treat blank as yes.
17. **Opt-out.** Lowercase `OptOut`; match `^(yes|y|true|1|stop|opted out|optout|unsubscribed|dnc)$` → reject `opted_out`. Lowercase `Status`; match `^(opted out|opt out|do not contact|dnc|stop|unsubscribed|suppressed)$` → reject `status_suppressed`; match `^(sent|done|complete|completed|skipped)$` → reject `status_already_processed`.
18. **Suppression.** **If** `Suppress` **contains** `Phone` → reject `on_suppression_list`.
19. **Duplicate in file.** **If** `SeenPhones` **contains** `Phone` → reject `duplicate_phone_in_file`.
20. **Category.** Lowercase `MType`. `Category` = `service` only if `MType` is `service` **and** (`Tpl` is `appointment_reminder`, `client_followup`, `general`, or blank-with-custom-message); otherwise `marketing`. **If** `Category` = `marketing` and (`ConsentDate` empty or `ConsentSrc` empty) → reject `marketing_needs_consent_date_and_source`. *(The Shortcut only checks non-empty; run `sms_prep.py check` first to validate the date format and reject future dates.)*
21. **Template/message resolution.** If `MsgCol` has text: `Tpl` must be blank, `custom`, or `general`; anything else → reject `message_conflicts_with_template`. If `MsgCol` is empty and `Tpl` is empty → reject `no_template_or_message`.

### Phase D: draft the message (no invented facts)
22. **Text** actions, one per template (select with **If Tpl is …**), using exactly the wording in `templates/templates.json`. Required fields empty → reject `missing_field:<name>`. Example, appointment_reminder:
    `Hi {First}, this is a reminder of your appointment with {Config.agent_name} at {Config.business_name} on {ApptDate} at {ApptTime}. Reply to confirm or reschedule.`
    `custom` → `MsgCol` as written. `general` → `Hi {First}, this is {agent_name} at {business_name}. {MsgCol}`. → **Set Variable** `Draft`. **No opt-out line is appended** (per your instruction; see `COMPLIANCE_NOTES.md`).
23. **Sensitive-data block.** **Match Text** on `Draft` with each pattern below; any match → reject `sensitive_data_in_message`:
    - `\b\d{3}-?\d{2}-?\d{4}\b`
    - `(?i)\b[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9][0-9]-?[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9][0-9]-?[AC-HJKMNP-RT-Y]{2}[0-9]{2}\b`
    - `\b(?:\d[ -]?){13,19}\b`
    - `(?i)\b(date of birth|dob|diagnos\w*|prescription\w*|medication\w*|policy number|account number|routing number|ssn|social security|bank account|password|pin code)\b`
24. **Review flags** → `Flags` text, `NeedsReview` yes/no:
    - `Category` = marketing → `marketing_content`
    - `(?i)(guaranteed|free|no cost|\$0|save|savings|lowest|best|cheaper|limited time|act now|urgent|last chance|you qualify|you're eligible|you are eligible|benefits|\$)` → `claims_or_promotional_language`
    - `(?i)\b(medicare|medigap|part d|part c|advantage|enroll|enrollment|aep)\b` → `medicare_reference_cms_rules`
    - **Count** characters > 320 → `long_message`
25. **Key.** **Text** `{Campaign}|{TplOrCustom}|{Phone}` → `Key`.
26. **Resume.** **If** `Processed` **contains** `Key` → `CountSkipped += 1`, skip row (silent). **Else if** `ApprovedOnly` **contains** `Key` → **Show Alert** "{First}: approved in an earlier run but no final outcome was logged. Check Messages > Sent before retrying." → **Choose from Menu** `Mark as sent (I checked)` / `Retry` / `Skip` → log accordingly.
27. **Add to Variable** `SeenPhones` ← `Phone` (only after passing all gates).

### Phase E: optional AI polish (only if `Mode` ≠ Template)
28. **Show Alert** "Send this draft and first name to {Mode}? No last name, phone number, notes or client records are sent." **Cancel** → use `Draft` unchanged.
29. Build the request exactly as in `docs/AI_PROVIDERS.md` (**Get Contents of URL**, POST). Read the key per that doc.
30. Take the reply text → `AIDraft`. **Guard (mirror of `ai_output_guard`)**: reject the AI text and keep `Draft` if length > 320, if it contains `$` and `Draft` doesn't, or if any number (`\d+` matches) is not also in `Draft`. If it passes → `Draft` = `AIDraft`, `NeedsReview` = yes, add flag `ai_edited`.

### Phase F: review and approve (every recipient, every time)
31. **If** `NeedsReview` = yes → **Choose from Menu** prompt `⚠ COMPLIANCE REVIEW: {Flags}\nTo: {First} {Last} {Phone}\n\n{Draft}` options `I reviewed, continue` / `Skip this one` / `Cancel run`.
32. **Repeat** 5 times (poor-man's loop; use variable `Done`): **If** `Done` ≠ yes →
    **Choose from Menu** prompt `To: {First} {Last}\n{Phone}\n\n{Draft}\n\nTemplate: {Tpl}  Category: {Category}` with:
    - **Approve** → log `approved`, **Add to** `approved_keys.txt`, go to Phase G, `Done` = yes.
    - **Edit** → **Ask for Input** (Default Answer = `Draft`) → `Draft`; re-run steps 23–24 on it; log `edited`; loop again.
    - **Skip** → log `skipped`, append `Key` to `processed_keys.txt`, `CountSkipped += 1`, `Done` = yes.
    - **Cancel run** → log `canceled` for this recipient, `CountCanceled += 1`, jump to Phase H (**Stop This Shortcut** after writing summary).
    *There is no auto-approve and no "send all" option anywhere.*

### Phase G: send (one recipient, one confirmation)
33. **Send Message**: Message = `Draft`, Recipients = `Phone`, **Show Compose Sheet = ON** (leave it on; you tap Send in Messages). Do not turn it off.
34. **Choose from Menu** "Did you tap Send in Messages for {First}?" options:
    - `Yes, I sent it` → log `sent_action_completed` (delivery_confirmed = `unknown`), append `Key` to `processed_keys.txt`, `CountSent += 1`.
    - `No, I canceled` → log `canceled`, `CountCanceled += 1` (key not marked processed → can be retried).
    - `It failed/errored` → log `failed`, `CountFailed += 1` (retryable).
    *The log never says "delivered." iOS gives Shortcuts no delivery receipt. See `IOS_LIMITATIONS.md`.*

### Logging action (used wherever it says "log")
**Text**: `"{ISO date}","{SessionID}","{Key}","{Phone}","{First} {Last}","{Tpl}","{Campaign}","{Status}","unknown","{Note}"` (use **Replace Text** `"` → `""` on name and note first) → **Append to File** (Shortcuts/TextFromSheet/send_log.csv, **Make New Line** ON, Overwrite OFF).
For rejects: Status = `blocked`, Note = reason, and also append `Key`/phone to `processed_keys.txt`.

### Phase H: summary
35. **Show Result**: `Sent: {CountSent} · Skipped: {CountSkipped} · Rejected: {CountRejected} · Canceled: {CountCanceled} · Failed: {CountFailed}\nLog: Files > iCloud Drive > Shortcuts > TextFromSheet > send_log.csv`.
36. Optional: **Save File** a copy of `send_log.csv` as `send_log_{SessionID}.csv` (timestamped archive).

## 3. After building
- Do **not** use *Share > Copy iCloud Link* on this shortcut if you ever paste a key into it. Shared shortcuts include their text actions.
- Run the tests in `TESTING_AND_TROUBLESHOOTING.md` with `data/sample_contacts.csv` and **your own phone number** as the only real recipient. Compose sheets mean nothing sends unless you tap Send.
