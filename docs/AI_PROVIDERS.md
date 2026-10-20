# AI personalization (optional; default is no AI)

**Default = "Template (no AI)".** It is free, offline, and never sends data anywhere. AI is optional
polish and always produces a *draft* that you still approve.

## What may be sent to an AI provider
Only: the contact's **first name** and the **already-rendered draft message**. Never: last name, phone
number, Notes, consent data, Status, policy/health/financial info, or the spreadsheet. The Python
reference (`ai_minimal_payload`) and its test enforce this shape. Get explicit authorization before
sending any real client's name to a third party, and check your own client-privacy obligations and
the provider's data terms. Run the first tests with fictional names.

## Keys: where they can and cannot live
Shortcuts has no encrypted key store, so be honest about the trade-off:
1. **Best available: paste at run time.** **Ask for Input** "API key" (or read the clipboard), use it, never save it. Nothing persists in the shortcut.
2. **Acceptable: a file outside iCloud.** Save the key in a text file in *Files > On My iPhone > Shortcuts* (not synced to iCloud), read it with **Get File** at run time. It is plain text on the phone; anyone with the unlocked phone could read it.
3. **Never:** put the key in a *Text* action inside the shortcut, in iCloud Drive, or in this repository (a test scans for key patterns). Shared shortcuts include their actions.

Use a key with a low spend limit set in the provider console. I have not tested key handling on a device.

## Claude (Anthropic Messages API)
**Get Contents of URL**: `https://api.anthropic.com/v1/messages`, Method **POST**, Request Body **JSON**.
Headers: `x-api-key` = the key, `anthropic-version` = `2023-06-01`, `content-type` = `application/json`.
Body:
```json
{
  "model": "claude-haiku-5-5",
  "max_tokens": 300,
  "system": "You lightly polish short text messages for a licensed insurance agent. Use ONLY the facts already in the draft. Do not add facts, numbers, dates, prices, plan names, benefits, health or financial details, promises, or urgency. Keep a friendly, professional tone, under 320 characters. Return only the message text.",
  "messages": [{"role": "user", "content": "First name: <First>\nDraft: <Draft>"}]
}
```
Reply path: **Get Dictionary Value** `content` → **Get Item from List** (first) → **Get Dictionary Value** `text`.
Check the current model ID and pricing at https://docs.claude.com before relying on `claude-haiku-5-5`.

## ChatGPT (OpenAI Chat Completions)
**Get Contents of URL**: `https://api.openai.com/v1/chat/completions`, POST, JSON. Header `Authorization` = `Bearer <key>`.
```json
{
  "model": "<OPENAI_MODEL_ID>",
  "messages": [
    {"role": "system", "content": "<same system text as above>"},
    {"role": "user", "content": "First name: <First>\nDraft: <Draft>"}
  ]
}
```
Reply path: `choices` → first item → `message` → `content`. Look up a current model ID on OpenAI's models page; I did not verify one.

## Output guard (always on)
AI text is discarded in favor of the template draft if it is longer than 320 characters, introduces `$`,
introduces any number not in the draft, or contains sensitive patterns (Python: `ai_output_guard`;
Shortcut: step 30). Any AI-edited message is automatically flagged for extra review.

## Cost
Template mode: $0. AI mode: provider charges per token (a one-sentence rewrite is a tiny amount) and
requires an API account separate from a Claude/ChatGPT chat subscription.
