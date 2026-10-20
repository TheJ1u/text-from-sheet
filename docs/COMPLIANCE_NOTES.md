# Compliance notes (not legal advice)

You asked for this to **not** append an opt-out line and noted it may not be used for insurance
clients. Done: no opt-out text is added to any message. If you later send marketing-type texts to
the public, talk to a compliance professional about whether one is required (TCPA, carrier rules,
state rules, and CMS Medicare marketing rules can all apply to insurance outreach).

## Checks that remain (they protect you regardless of audience)
These are about *who* you text and *what data* goes in a message, not message wording:
- Affirmative `Consent` required on every row (blank = no).
- `Opt Out`, `Status`, and `suppression_list.csv` checks: if someone told you to stop, they are never queued.
- Duplicate numbers, and "already sent" rows, are blocked.
- Sensitive data (SSN, Medicare ID, card/account numbers, health/financial terms) blocks a message.
- Marketing-type messages need consent date + source, and promotional or Medicare wording is flagged for your manual review.

## If you want fewer gates
- To make the opt-out line optional again: set `optout_text` in `data/config.json` (e.g. `"Reply STOP to opt out."`) and add ` {optout}` to a template body. In the Shortcut, append it in step 22.
- To drop the consent requirement for personal, non-business use, remove step 16 and the `Consent` column check (Python: delete the `no_affirmative_consent` rule in `process`). I did not do this because you didn't ask for it; say the word and I will.
- Texting someone who has told you to stop can still be a problem for personal use too, so I'd keep the suppression check.

## What the tool never does
It never sends protected health information or sensitive financial details, never assumes someone is
eligible for marketing because they appear in a spreadsheet, and never sends without you tapping Send.
