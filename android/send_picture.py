#!/usr/bin/env python3
"""send_picture.py - text a picture (or small file) plus a message to each person, one at a time.

Android does not let an ordinary app send picture texts (MMS) by itself in the background, so this is
"you tap Send" mode: for each person it opens your Messages app with the number, the message and the
picture already filled in. You press Send there, come back to Termux, and press Enter for the next person.
The number is also copied, in case your Messages app doesn't fill in the To field.

  python3 android/send_picture.py list.csv --message-file message.txt --campaign flyer --attach ~/storage/downloads/picture.jpg

Same safety rules as the text sender: skips bad/duplicate/opted-out/do-not-text numbers, only 8am-6pm,
never re-sends to someone already marked sent in this batch, logs everything, typed YES to begin.
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import send_slow as ss  # noqa: E402
import sms_prep as sp  # noqa: E402

OK_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "text/vcard", "text/x-vcard")
SHARED_PREFIXES = ("/storage/", "/sdcard/")


def mime_of(path: Path) -> str:
    t, _ = mimetypes.guess_type(str(path))
    if path.suffix.lower() == ".vcf":
        return "text/vcard"
    if path.suffix.lower() == ".heic":
        return "image/heic"
    return t or "application/octet-stream"


def attachment_notes(path: Path, mime: str) -> list:
    notes = []
    if mime == "application/pdf":
        notes.append("Many phones and carriers can't text a PDF. A link to the file in your message is more reliable.")
    elif mime not in OK_TYPES:
        notes.append("This kind of file often can't be sent by text. A link is more reliable.")
    size = path.stat().st_size
    if size > 1_500_000:
        notes.append(f"Big file ({size / 1e6:.1f} MB). Messages usually shrinks pictures; other files may be too big.")
    return notes


def shareable_path(path: Path, shared_dir: Path) -> Path:
    """Messages can only open files in shared storage (like Downloads). Copy there if needed."""
    real = os.path.realpath(path)
    if real.startswith(SHARED_PREFIXES):
        return Path(real)
    shared_dir.mkdir(parents=True, exist_ok=True)
    dst = shared_dir / ("text-tool-attachment" + path.suffix.lower())
    shutil.copyfile(path, dst)
    return Path(os.path.realpath(dst))


def intent_command(phone: str, text: str, path: Path, mime: str) -> list:
    """The Android 'share to Messages' request, with the number and text pre-filled where the app supports it."""
    return ["am", "start", "-a", "android.intent.action.SEND", "-t", mime,
            "--es", "address", phone, "--es", "sms_body", text, "--es", "android.intent.extra.TEXT", text,
            "--eu", "android.intent.extra.STREAM", "file://" + str(path), "--grant-read-uri-permission"]


def android_launcher(phone, text, path, mime):
    if shutil.which("termux-clipboard-set"):
        subprocess.run(["termux-clipboard-set", phone], capture_output=True, timeout=15)
    try:
        p = subprocess.run(intent_command(phone, text, path, mime), capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return False, f"error: {exc}"
    err = (p.stderr or "").strip()
    return (p.returncode == 0 and "Error" not in err), (err or "opened")[:200]


def walk(ready, launcher, ask, log_path, campaign, attach: Path, mime, out=print, now_fn=datetime.now,
         window=ss.DEFAULT_WINDOW):
    """One person at a time. Returns counts. ask() gets the reply typed after each person."""
    sent = skipped = later = 0
    for i, item in enumerate(ready, start=1):
        if not ss.item_ok_now(item, now_fn, window):
            later += 1
            out(f"[{i}/{len(ready)}] {item['name']}: outside 8am-6pm for them; left for later.")
            continue
        out(f"\n[{i}/{len(ready)}] {item['name']} {item['phone']}")
        out(f"  Message: {item['message']}")
        ok, note = launcher(item["phone"], item["message"], attach, mime)
        if not ok:
            out(f"  Couldn't open Messages ({note}). Stopping so you can check.")
            return {"sent": sent, "skipped": skipped, "later": later, "stopped": "could not open Messages"}
        out("  Messages is open with the picture. If the To field is empty, paste (the number is copied).")
        reply = (ask("  Pressed Send? Enter = yes, next person. s = skip. q = quit: ") or "").strip().lower()
        status = {"": "submitted", "s": "skipped", "q": None}.get(reply, "submitted" if reply in ("y", "yes") else "skipped")
        if reply == "q":
            out("Stopped. Run it again to continue; people marked sent won't get it twice.")
            return {"sent": sent, "skipped": skipped, "later": later, "stopped": "you quit"}
        ss.append_log(log_path, {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "campaign": campaign,
            "phone": item["phone"], "name": item["name"], "status": status, "delivery_confirmed": "unknown",
            "note": f"with {attach.name}; sent by you in Messages" if status == "submitted" else "skipped by you",
            "message": item["message"]})
        sent += status == "submitted"
        skipped += status == "skipped"
    return {"sent": sent, "skipped": skipped, "later": later, "stopped": None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("contacts")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--message")
    g.add_argument("--message-file")
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--attach", required=True, help="the picture or file to send with every message")
    ap.add_argument("--window-start", type=int, default=ss.DEFAULT_WINDOW[0])
    ap.add_argument("--window-end", type=int, default=ss.DEFAULT_WINDOW[1])
    ap.add_argument("--country-code", default="1")
    ap.add_argument("--fallback", default="")
    ap.add_argument("--suppression")
    ap.add_argument("--require-consent", action="store_true")
    ap.add_argument("--log", default="send_log.csv")
    ap.add_argument("--shared-dir", default=str(Path.home() / "storage" / "downloads"),
                    help="where to copy the file so Messages can open it")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    window = (args.window_start, args.window_end)
    if not (0 <= window[0] < window[1] <= 24):
        print("Send window must satisfy 0 <= start < end <= 24.")
        return 2
    attach = Path(args.attach).expanduser()
    if not attach.is_file():
        print(f"Picture/file not found: {attach}. Save it in Downloads (for example picture.jpg).")
        return 2
    if args.suppression and not Path(args.suppression).exists():
        print(f"Do-not-text file not found: {args.suppression}. Refusing to continue.")
        return 2
    mime = mime_of(attach)
    template = args.message if args.message is not None else Path(args.message_file).read_text(encoding="utf-8").strip()
    log_path = Path(args.log)
    plan = ss.build_plan(sp.read_contacts(Path(args.contacts)), template, args.country_code,
                         sp.load_suppression(args.suppression, args.country_code),
                         ss.load_done_phones(log_path, args.campaign), args.fallback, args.require_consent)
    ready, rej = plan["ready"], plan["rejected"]
    print(f"\nPicture/file: {attach.name} ({mime}, {max(1, attach.stat().st_size // 1024)} KB)")
    for n in attachment_notes(attach, mime):
        print("Note: " + n)
    print(f"Ready: {len(ready)}   Skipped: {len(rej)}   Already sent in this batch: {plan['already_done']}")
    for r in rej[:10]:
        print(f"  skipped row {r['row']} ({r['name']}): {ss.plain_reason(r['reasons'])}")
    print("\nPreview:")
    for item in ready[:3]:
        print(f"  To {item['name']} {item['phone']}: {item['message']}  [+ {attach.name}]")
    print("\nFor each person, Messages opens with everything filled in. You press Send, come back, press Enter.")
    if args.dry_run:
        print("\nDry run: nothing opened, nothing written.")
        return 0
    if not ready:
        print("Nothing to send.")
        return 0
    if not shutil.which("am"):
        print("The Android 'am' command isn't available. This only works inside Termux on the phone.")
        return 2
    if input("\nType YES to confirm you have permission to text these people: ").strip() != "YES":
        print("Cancelled.")
        return 1
    shared = shareable_path(attach, Path(args.shared_dir).expanduser())
    res = walk(ready, android_launcher, input, log_path, args.campaign, shared, mime, window=window)
    print(f"\nDone: {res['sent']} marked sent, {res['skipped']} skipped, {res['later']} left for later."
          + (f" Stopped: {res['stopped']}." if res["stopped"] else ""))
    print(f"Log: {log_path}. 'submitted' here means you said you pressed Send; delivery isn't confirmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
