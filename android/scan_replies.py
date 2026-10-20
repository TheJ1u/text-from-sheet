#!/usr/bin/env python3
"""scan_replies.py - find people on your list who texted back "stop" / "remove me" and add them to do_not_text.csv.

  python3 android/scan_replies.py list.csv --suppression do_not_text.csv

Reads the phone's received texts with `termux-sms-list` (Termux:API), looks only at numbers that are on
your list, and shows who asked not to be texted. You type YES to add the clear ones. Unclear replies
(like "stop by tomorrow" or "wrong number") are listed for you to read; nothing is added for those.
Nothing is sent. Nothing leaves the phone.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sms_prep as sp  # noqa: E402

EXACT = {"stop", "stop all", "stopall", "unsubscribe", "cancel", "end", "quit", "optout", "opt out",
         "remove", "remove me", "no more", "no thanks stop", "stop please", "please stop"}
PHRASES = re.compile(
    r"\b(stop (texting|messaging|contacting|sending|text)|do not (text|contact|message|call)|"
    r"don'?t (text|contact|message)|dont (text|contact|message)|remove (me|my number)|take me off|"
    r"unsubscribe|opt ?out|leave me alone|no more (texts|messages))\b", re.I)
MAYBE = re.compile(r"\b(stop|wrong number|who is this|who's this|not interested|no thank)\b", re.I)


def classify(body: str) -> str:
    """'definite', 'maybe' or ''."""
    b = re.sub(r"[^a-z' ]", "", (body or "").lower()).strip()
    b = re.sub(r"\s+", " ", b)
    if b in EXACT or PHRASES.search(body or ""):
        return "definite"
    if MAYBE.search(body or ""):
        return "maybe"
    return ""


def scan(messages, list_phones, cc="1"):
    """messages: dicts like termux-sms-list output. Returns (definite {phone: body}, maybe {phone: body})."""
    definite, maybe = {}, {}
    for m in messages:
        if str(m.get("type", "inbox")).lower() not in {"inbox", "1"}:
            continue
        e164, err = sp.normalize_phone(str(m.get("number", "")), cc)
        if err or e164 not in list_phones:
            continue
        kind = classify(m.get("body", ""))
        if kind == "definite":
            definite[e164] = m.get("body", "")
            maybe.pop(e164, None)
        elif kind == "maybe" and e164 not in definite:
            maybe[e164] = m.get("body", "")
    return definite, maybe


def existing(path: Path, cc="1") -> set:
    return sp.load_suppression(str(path), cc) if path.exists() else set()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("contacts")
    ap.add_argument("--suppression", default="do_not_text.csv")
    ap.add_argument("--country-code", default="1")
    ap.add_argument("--from-json", help="read messages from a JSON file instead of the phone (for testing)")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args(argv)

    if args.from_json:
        messages = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    else:
        if not shutil.which("termux-sms-list"):
            print("termux-sms-list not found. Install Termux:API (app) and `pkg install termux-api`.")
            return 2
        try:
            p = subprocess.run(["termux-sms-list", "-l", str(args.limit), "-t", "inbox"],
                               capture_output=True, text=True, timeout=60)
            messages = json.loads(p.stdout or "[]")
        except Exception as exc:
            print(f"Couldn't read texts ({exc}). Check Termux:API has the SMS permission.")
            return 2
    names, phones = {}, set()
    for _, r, _extra in sp.read_contacts(Path(args.contacts)):
        e164, err = sp.normalize_phone(r.get("phone", ""), args.country_code)
        if e164:
            phones.add(e164)
            names[e164] = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip() or e164
    already = existing(Path(args.suppression), args.country_code)
    definite, maybe = scan(messages, phones, args.country_code)
    new = {p: b for p, b in definite.items() if p not in already}
    print(f"Checked {len(messages)} received texts against {len(phones)} numbers on your list.")
    if not new and not maybe:
        print("No one has asked to stop.")
        return 0
    for p, b in new.items():
        print(f"  ASKED TO STOP: {names.get(p, p)} {p}: \"{b[:80]}\"")
    for p, b in maybe.items():
        if p not in already:
            print(f"  READ THIS ONE (not added): {names.get(p, p)} {p}: \"{b[:80]}\"")
    if not new:
        return 0
    if input(f"\nType YES to add the {len(new)} 'asked to stop' number(s) to {args.suppression}: ").strip() != "YES":
        print("Nothing added.")
        return 1
    path = Path(args.suppression)
    if not path.exists():
        path.write_text("Phone\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as f:
        for p in new:
            f.write(p + "\n")
    print("Added. They will never be texted by this tool. If a send is running, Stop then Start it again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
