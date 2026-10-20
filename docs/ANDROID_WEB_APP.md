# Text From Sheet: Android (and any phone) web version

One file: `web/index.html`. No install, no account, no server. Host it anywhere that serves static
files (Vercel, GitHub Pages, Netlify) and text people the link.

## What the person sees
1. Tap the link → page opens in their phone's browser.
2. **Choose CSV file** (or paste numbers). It needs a phone column; other columns (First Name, Event, …) become message fields.
3. Write a message. Tap chips like `{first_name}` to insert a name; preview updates live. Optional: fallback text for blanks, optional opt-out line (off by default).
4. Tick "I have permission to text these people," tap **Start reviewing**.
5. For each person: edit the text if wanted → **Open in Messages** (their SMS app opens pre-filled) → they tap **Send** → back in the page tap **Sent ✓ Next** or **Skip**.
6. **Download log** gives a CSV of what they marked.

Texts come from the **user's own phone number**, one at a time, because the web page can only open the messaging app pre-filled. That is also why it cannot silently send or send to everyone at once.

## Privacy
The CSV is read in the browser and never uploaded; the page has no network code (tested). Progress is saved in that browser's local storage on that phone so people can resume; "Start over" clears it.

## Safeguards built in
Invalid / Excel-damaged numbers skipped with a reason; duplicates removed; rows marked opted-out (columns like `Opt Out`, `Unsubscribed`, `Do Not Text`) skipped; if a `Consent` column exists, non-"yes" rows skipped; unfilled `{placeholders}` and SSN/card-number-looking text block the Open button; nothing is invented for blank fields unless the user types a fallback.

## Not verified
- **Not tested on a physical Android phone.** Logic and flow pass in a simulated browser only (`NODE_PATH=<jsdom> node tests/web_test.js`, 13 tests).
- `sms:` links with `?body=` are the standard way to pre-fill Android's Messages; most default SMS apps honor them, but some browsers/apps ask "open with" or drop the body. Try Chrome + Google Messages and Samsung Messages first.
- Very long messages may split or turn into MMS depending on the carrier/app.
- The log records what the person tapped, not delivery.
- iPhone: the same page should work (it uses `&body=` on iOS), also untested.
