#!/usr/bin/env python3
"""send_slow.py - paced bulk texting from an Android phone's own number, via Termux.

Plan once, approve once, then it sends ONE text per interval (default 65 s, minimum 60 s) from the
phone's own number, only between 8am and 6pm phone-local time (it pauses overnight and resumes the next
morning by itself), keeps a log after every message, and can be stopped any time. Re-running the same
command resumes where it left off (it never re-texts a number already marked submitted).

  python3 android/send_slow.py contacts.csv --message "Hi {first_name}, are you free Friday?" \
      --campaign church-dinner --dry-run          # preview only; sends nothing
  python3 android/send_slow.py contacts.csv --message-file msg.txt --campaign church-dinner

Safety rules built in (not optional):
  * 60-second minimum between texts (Android and carriers limit fast sending; this respects that).
  * Send window (default 8am-6pm, phone's local time). Outside it, it waits; it never sends at night.
  * No per-run cap by default (use --max-per-run N if you want one).
  * Needs a typed YES (permission) and typed SEND after you see the preview. No --yes flag.
  * Skips invalid/duplicate/opted-out numbers; never invents missing names; blocks SSN/card-like text.
  * Stops after 3 failures in a row. Stop any time: Ctrl-C, or create a file named STOP.
  * The log says "submitted" (the phone accepted it for sending). It cannot confirm delivery.
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sms_prep as sp  # noqa: E402  (normalize_phone, find_sensitive, read_contacts, constants)

MIN_INTERVAL = 60
DEFAULT_INTERVAL = 65
DEFAULT_MAX_PER_RUN = 0          # 0 = no limit
DEFAULT_WINDOW = (8, 18)         # send only from 08:00 up to (not including) 18:00, phone-local time
MAX_CONSECUTIVE_FAILURES = 3
LOG_FIELDS = ["timestamp", "campaign", "phone", "name", "status", "delivery_confirmed", "note", "message"]


def key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


ALIASES = {"first": "firstname", "last": "lastname", "fullname": "name"}


def render(template: str, vals: dict, fallback: str = ""):
    missing = []

    def sub(m):
        tok = m.group(1)
        k = ALIASES.get(key(tok), key(tok))
        v = vals.get(k, "")
        if v:
            return v
        if fallback:
            return fallback
        missing.append(tok.strip())
        return m.group(0)

    return re.sub(r"\{([^{}]+)\}", sub, template).strip(), missing


def message_issues(text: str) -> list:
    out = []
    if not text.strip():
        out.append("empty_message")
    if re.search(r"\{[^{}]+\}", text):
        out.append("unfilled_placeholder")
    out += sp.find_sensitive(text)
    return out


def load_done_phones(log_path: Path, campaign: str) -> set:
    done = {}
    if log_path.exists():
        with open(log_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("campaign") == campaign:
                    done[r.get("phone", "")] = r.get("status", "")
    return {p for p, s in done.items() if s == "submitted"}


def build_plan(rows, template, cc="1", suppression=frozenset(), done=frozenset(), fallback=""):
    ready, rejected, already = [], [], 0
    seen = set()
    for row_no, r, extra in rows:
        name = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()

        def reject(*why):
            rejected.append({"row": row_no, "name": name or r.get("phone", ""), "reasons": ";".join(why)})

        if extra:
            reject("malformed_row_check_commas")
            continue
        e164, err = sp.normalize_phone(r.get("phone", ""), cc)
        if err:
            reject(err)
            continue
        if r.get("opt_out", "").strip().lower() in sp.OPT_OUT_TRUE:
            reject("opted_out")
            continue
        status = r.get("status", "").strip().lower()
        if status in sp.STATUS_SUPPRESSED:
            reject("status_suppressed")
            continue
        if "consent" in r and r["consent"].strip().lower() not in sp.AFFIRMATIVE_CONSENT:
            reject("no_affirmative_consent")
            continue
        if e164 in suppression:
            reject("on_suppression_list")
            continue
        if e164 in seen:
            reject("duplicate_phone")
            continue
        vals = {key(k): v.strip() for k, v in r.items() if isinstance(v, str)}
        vals["name"] = vals.get("name") or name
        text, missing = render(template, vals, fallback)
        if missing:
            reject("missing_field:" + ",".join(missing))
            continue
        bad = message_issues(text)
        if bad:
            reject(*bad)
            continue
        seen.add(e164)
        if e164 in done:
            already += 1
            continue
        ready.append({"phone": e164, "name": name or e164, "message": text})
    return {"ready": ready, "rejected": rejected, "already_done": already}


def termux_sender(sim=None):
    def send(phone, text):
        cmd = ["termux-sms-send", "-n", phone]
        if sim:
            cmd += ["-s", str(sim)]
        cmd.append(text)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as exc:  # timeout, missing binary, ...
            return False, f"error: {exc}"
        return (p.returncode == 0), (p.stderr.strip() or p.stdout.strip() or "ok")[:200]
    return send


def log_stats(log_path: Path, campaign: str) -> dict:
    stats = {"submitted": 0, "failed": 0, "last": ""}
    if log_path.exists():
        with open(log_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("campaign") == campaign:
                    if r.get("status") == "submitted":
                        stats["submitted"] += 1
                    elif r.get("status") == "failed":
                        stats["failed"] += 1
                    stats["last"] = r.get("timestamp", "")
    return stats


def termux_notifier():
    """Live progress in the phone's notification shade (needs Termux:API). Returns None if unavailable."""
    if not shutil.which("termux-notification"):
        return None

    def notify(text):
        cmd = ["termux-notification", "--id", "texttool", "--title", "Texting", "--content", text]
        if not text.startswith("Finished"):
            cmd.append("--ongoing")
        subprocess.run(cmd, capture_output=True, timeout=15)
    return notify


def append_log(log_path: Path, row: dict):
    new = not log_path.exists()
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def in_window(now: datetime, window) -> bool:
    start, end = window
    return start <= now.hour < end


def next_window_open(now: datetime, window) -> datetime:
    start, _ = window
    opens = now.replace(hour=start, minute=0, second=0, microsecond=0)
    return opens if opens > now else opens + timedelta(days=1)


def estimate(n: int, interval: int, window) -> str:
    per_day = max(((window[1] - window[0]) * 3600) // interval, 1)
    days = -(-n // per_day)
    return f"about {n * interval / 3600:.1f} hours of sending, spread over {days} day{'s' if days != 1 else ''}"


def run(ready, sender, sleep, log_path, campaign, interval, max_per_run, stop_file, out=print,
        now_fn=datetime.now, window=DEFAULT_WINDOW, notify=None):
    interval = max(int(interval), MIN_INTERVAL)
    batch = ready[:max_per_run] if max_per_run else list(ready)
    sent = failed = consec = 0
    stopped = None

    def tell(msg):
        if notify:
            try:
                notify(msg)
            except Exception:
                pass  # a notification problem must never stop or change sending
    for i, item in enumerate(batch):
        if Path(stop_file).exists():
            stopped = "STOP file found"
            break
        announced = False
        while not in_window(now_fn(), window):          # outside 8am-6pm: wait, never send
            if not announced:
                out(f"Outside the send window; waiting until {next_window_open(now_fn(), window):%a %I:%M %p}.")
                tell(f"{sent + failed} of {len(batch)} done. Paused until {next_window_open(now_fn(), window):%a %I:%M %p}.")
                announced = True
            if Path(stop_file).exists():
                break
            sleep(30)
        if Path(stop_file).exists():
            stopped = "STOP file found"
            break
        ok, note = sender(item["phone"], item["message"])
        append_log(log_path, {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "campaign": campaign,
            "phone": item["phone"], "name": item["name"], "status": "submitted" if ok else "failed",
            "delivery_confirmed": "unknown", "note": note, "message": item["message"]})
        if ok:
            sent += 1
            consec = 0
        else:
            failed += 1
            consec += 1
            if consec >= MAX_CONSECUTIVE_FAILURES:
                stopped = f"{MAX_CONSECUTIVE_FAILURES} failures in a row (check SMS permission / signal)"
                break
        tell(f"{sent + failed} of {len(batch)} done" + (f", {failed} failed" if failed else "") + f". Last: {item['name']}")
        out(f"[{i + 1}/{len(batch)}] {item['name']}: {'submitted' if ok else 'FAILED - ' + note}")
        if i < len(batch) - 1:
            for _ in range(interval):
                if Path(stop_file).exists():
                    break
                sleep(1)
    left = len(ready) - sent - failed
    tell(f"Finished: {sent} submitted, {failed} failed" + (f", {max(left, 0)} still to go" if left > 0 else "") + ".")
    return {"submitted": sent, "failed": failed, "remaining_in_list": max(left, 0), "stopped": stopped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("contacts")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--message")
    g.add_argument("--message-file")
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help=f"seconds between texts (min {MIN_INTERVAL})")
    ap.add_argument("--max-per-run", type=int, default=DEFAULT_MAX_PER_RUN, help="0 = no limit (default)")
    ap.add_argument("--window-start", type=int, default=DEFAULT_WINDOW[0], help="first hour to send, 0-23 (default 8)")
    ap.add_argument("--window-end", type=int, default=DEFAULT_WINDOW[1], help="no sending at or after this hour, 1-24 (default 18)")
    ap.add_argument("--country-code", default="1")
    ap.add_argument("--fallback", default="", help="text to use when a {field} is blank (otherwise that person is held back)")
    ap.add_argument("--suppression", help="CSV of numbers never to text")
    ap.add_argument("--log", default="send_log.csv")
    ap.add_argument("--sim", help="SIM slot (1 or 2) on dual-SIM phones")
    ap.add_argument("--status", action="store_true", help="show progress for this campaign and exit")
    ap.add_argument("--dry-run", action="store_true", help="preview only; sends nothing, writes nothing")
    args = ap.parse_args(argv)

    if not (0 <= args.window_start < args.window_end <= 24):
        print("Send window must satisfy 0 <= start < end <= 24 (hours, phone-local time).")
        return 2
    window = (args.window_start, args.window_end)
    if args.suppression and not Path(args.suppression).exists():
        print(f"Do-not-text file not found: {args.suppression}. Refusing to continue, because a missing "
              "file would silently skip your do-not-text list. Fix the name or create the file.")
        return 2
    if args.interval < MIN_INTERVAL:
        print(f"Interval raised to the {MIN_INTERVAL}-second minimum.")
    template = args.message if args.message is not None else Path(args.message_file).read_text(encoding="utf-8").strip()
    log_path = Path(args.log)
    plan = build_plan(sp.read_contacts(Path(args.contacts)), template, args.country_code,
                      sp.load_suppression(args.suppression, args.country_code),
                      load_done_phones(log_path, args.campaign), args.fallback)
    ready, rej = plan["ready"], plan["rejected"]
    if args.status:
        st = log_stats(log_path, args.campaign)
        total = len(ready) + plan["already_done"]
        print(f"Campaign '{args.campaign}': {st['submitted']} of {total} submitted, {len(ready)} still to go, "
              f"{st['failed']} failed attempts. Last activity: {st['last'] or 'none yet'}.")
        print(f"Send window {window[0]:02d}:00-{window[1]:02d}:00; it is {datetime.now():%a %I:%M %p} on this phone now.")
        return 0
    interval = max(args.interval, MIN_INTERVAL)
    this_run = min(len(ready), args.max_per_run) if args.max_per_run else len(ready)

    print(f"\nReady to text: {len(ready)}   Skipped: {len(rej)}   Already done (earlier run): {plan['already_done']}")
    for r in rej[:10]:
        print(f"  skipped row {r['row']} ({r['name']}): {r['reasons']}")
    if len(rej) > 10:
        print(f"  ...and {len(rej) - 10} more")
    print("\nPreview:")
    for item in ready[:3]:
        print(f"  To {item['name']} {item['phone']}: {item['message']}")
    odd = [i for i in ready if not i["message"].isascii()]
    long_ = [i for i in ready if len(i["message"]) > 160]
    if odd:
        print(f"\nNote: {len(odd)} message(s) contain curly quotes, emoji or accents. Those send as shorter "
              "70-character pieces and may be split into several texts.")
    if long_:
        print(f"Note: {len(long_)} message(s) are over 160 characters and may go out as several linked texts.")
    print(f"\nThis run: {this_run} texts, one every {interval}s, {estimate(this_run, interval, window)}.")
    print(f"Sends only {window[0]:02d}:00-{window[1]:02d}:00 phone-local time; pauses overnight and resumes by itself."
          f" It is {datetime.now():%a %I:%M %p} on this phone now.")
    if not in_window(datetime.now(), window):
        print(f"Not in the send window now, so it will wait until {next_window_open(datetime.now(), window):%a %I:%M %p}.")

    if args.dry_run:
        print("\nDry run: nothing sent, nothing written.")
        return 0
    if not ready:
        print("Nothing to send.")
        return 0
    if not shutil.which("termux-sms-send"):
        print("termux-sms-send not found. Install Termux:API (app) and `pkg install termux-api`. See docs/ANDROID_TERMUX.md.")
        return 2

    if input("\nType YES to confirm you have permission to text these people: ").strip() != "YES":
        print("Cancelled.")
        return 1
    if input("Type SEND to start (you can stop any time with Ctrl-C or by creating a file named STOP): ").strip() != "SEND":
        print("Cancelled.")
        return 1

    stop_file = Path("STOP")
    if stop_file.exists():
        stop_file.unlink()
    if shutil.which("termux-wake-lock"):
        subprocess.run(["termux-wake-lock"], check=False)
    try:
        res = run(ready, termux_sender(args.sim), time.sleep, log_path, args.campaign,
                  interval, args.max_per_run, stop_file, window=window, notify=termux_notifier())
    except KeyboardInterrupt:
        print("\nStopped by you. Progress is saved; run the same command to resume.")
        return 130
    finally:
        if shutil.which("termux-wake-unlock"):
            subprocess.run(["termux-wake-unlock"], check=False)
    print(f"\nDone: {res['submitted']} submitted, {res['failed']} failed, {res['remaining_in_list']} still to go."
          + (f" Stopped: {res['stopped']}." if res["stopped"] else ""))
    print(f"Log: {log_path}  (status 'submitted' means the phone accepted it; delivery is not confirmed)")
    if res["remaining_in_list"]:
        print("Run the same command again to continue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
