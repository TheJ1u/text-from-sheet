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
import calendar
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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


def build_plan(rows, template, cc="1", suppression=frozenset(), done=frozenset(), fallback="", require_consent=False):
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
        if ("consent" in r or require_consent) and r.get("consent", "").strip().lower() not in sp.AFFIRMATIVE_CONSENT:
            reject("no_affirmative_consent" if "consent" in r else "no_consent_column")
            continue
        tz = (r.get("timezone") or r.get("time zone") or "").strip()
        if tz:
            try:
                ZoneInfo(tz)
            except Exception:
                reject("unknown_timezone:" + tz)
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
        ready.append({"phone": e164, "name": name or e164, "message": text, "tz": tz})
    return {"ready": ready, "rejected": rejected, "already_done": already}


BDAY_KEYS = ("birthday", "birth date", "birthdate", "dob", "date of birth", "bday")
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def parse_birthday(raw):
    """Return (month, day) from 03/14, 3/14/1948, 1948-03-14, '1948-03-14 00:00:00' (Excel), 'March 14', or None.
    Numeric dates are read US-style (month first)."""
    t = (raw or "").strip()
    if not t:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$", t)
    if m:
        mo, d = int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", t)
        if m:
            mo, d = int(m.group(1)), int(m.group(2))
        else:
            m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*\d{2,4})?$", t)
            if not m or m.group(1).lower() not in MONTHS:
                return None
            mo, d = MONTHS[m.group(1).lower()], int(m.group(2))
    if not (1 <= mo <= 12) or not (1 <= d <= calendar.monthrange(2000, mo)[1]):   # 2000 is a leap year
        return None
    return mo, d


def is_birthday_today(md, today) -> bool:
    if md is None:
        return False
    if md == (today.month, today.day):
        return True
    return md == (2, 29) and (today.month, today.day) == (2, 28) and not calendar.isleap(today.year)


def birthday_of(row: dict):
    for k in BDAY_KEYS:
        if row.get(k, "").strip():
            return parse_birthday(row[k])
    return None


def filter_birthdays(rows, today):
    """Keep rows whose birthday is today. Returns (rows_today, rows_with_readable_birthday, unreadable_count)."""
    todays, readable, bad = [], [], 0
    for row in rows:
        md = birthday_of(row[1])
        if md is None:
            bad += 1
            continue
        readable.append(row)
        if is_birthday_today(md, today):
            todays.append(row)
    return todays, readable, bad


def fingerprint(template, campaign, window, require_consent) -> str:
    blob = json.dumps({"t": template, "c": campaign, "w": list(window), "rc": bool(require_consent)}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_approval(path: Path, template, campaign, window, require_consent, now):
    path.write_text(json.dumps({"fingerprint": fingerprint(template, campaign, window, require_consent),
                                "approved_at": now.isoformat(timespec="seconds"), "campaign": campaign,
                                "window": list(window), "message": template}, indent=2), encoding="utf-8")


def approval_ok(path: Path, template, campaign, window, require_consent):
    """(True, '') when the saved approval matches this exact message and rules; else (False, why)."""
    if not path.exists():
        return False, "no saved approval yet (run the birthday setup and type YES and SEND once)"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False, "approval file unreadable"
    if saved.get("fingerprint") != fingerprint(template, campaign, window, require_consent):
        return False, "the message or rules changed since you approved them; approve again"
    return True, ""


def acquire_lock(path: Path) -> bool:
    """Only one automatic run at a time. A lock left by a dead process is cleaned up."""
    if path.exists():
        try:
            os.kill(int(path.read_text().strip()), 0)
            return False
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
    path.write_text(str(os.getpid()))
    return True


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


def now_for(now_fn, tz: str):
    """Current time for a recipient. No timezone given = the phone's own clock."""
    n = now_fn()
    return n.astimezone(ZoneInfo(tz)) if tz else n


def item_ok_now(item, now_fn, window) -> bool:
    return in_window(now_for(now_fn, item.get("tz", "")), window)


def estimate(n: int, interval: int, window) -> str:
    per_day = max(((window[1] - window[0]) * 3600) // interval, 1)
    days = -(-n // per_day)
    return f"about {n * interval / 3600:.1f} hours of sending, spread over {days} day{'s' if days != 1 else ''}"


def send_test(ready, to_number, sender, log_path, campaign, cc="1"):
    """Send ONE text (the first person's message, as it would really go) to the user's own number."""
    e164, err = sp.normalize_phone(to_number, cc)
    if err:
        return False, f"your number is not valid: {err}"
    if not ready:
        return False, "no ready messages to test with"
    text = ready[0]["message"]
    ok, note = sender(e164, text)
    append_log(log_path, {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "campaign": f"{campaign}-test", "phone": e164, "name": "TEST TO SELF",
                          "status": "submitted" if ok else "failed", "delivery_confirmed": "unknown",
                          "note": note, "message": text})
    return ok, text if ok else note


def run(ready, sender, sleep, log_path, campaign, interval, max_per_run, stop_file, out=print,
        now_fn=datetime.now, window=DEFAULT_WINDOW, notify=None, same_day_only=False):
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
    pending = list(batch)
    done_n = 0
    start_date = now_fn().date()
    while pending:
        if Path(stop_file).exists():
            stopped = "STOP file found"
            break
        announced = False
        item = None
        day_over = False
        while item is None:                              # next person whose own 8am-6pm window is open
            item = next((x for x in pending if item_ok_now(x, now_fn, window)), None)
            if item is not None:
                break
            if not announced:
                if not pending[0].get("tz"):
                    when = f"until {next_window_open(now_fn(), window):%a %I:%M %p}"
                else:
                    when = "for the next recipient's send window"
                out(f"Outside the send window; waiting {when}.")
                tell(f"{sent + failed} of {len(batch)} done. Paused, waiting {when}.")
                announced = True
            if Path(stop_file).exists():
                break
            sleep(30)
            if same_day_only and now_fn().date() != start_date:
                day_over = True
                break
        if day_over:
            stopped = "the day ended (birthday texts are only sent on the day)"
            break
        if item is None or Path(stop_file).exists():
            stopped = "STOP file found"
            break
        if same_day_only and now_fn().date() != start_date:
            stopped = "the day ended (birthday texts are only sent on the day)"
            break
        pending.remove(item)
        done_n += 1
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
        out(f"[{done_n}/{len(batch)}] {item['name']}: {'submitted' if ok else 'FAILED - ' + note}")
        if pending:
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
    ap.add_argument("--require-consent", action="store_true",
                    help="refuse anyone unless a Consent column says yes (also refuses lists with no Consent column)")
    ap.add_argument("--test-to", metavar="NUMBER", help="send ONE test text (first person's message) to your own number, then exit")
    ap.add_argument("--birthdays-today", action="store_true",
                    help="only people whose Birthday column is today; the batch name gets the year added, so nobody is texted twice a year")
    ap.add_argument("--approve-auto", action="store_true",
                    help="approve this exact message and rules ONCE (typed YES and SEND) so --auto may run unattended")
    ap.add_argument("--auto", action="store_true",
                    help="unattended run (for a daily timer). Only with --birthdays-today, only with a saved matching approval")
    ap.add_argument("--approval-file", default="auto_approval.json")
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
    if (args.auto or args.approve_auto) and not args.birthdays_today:
        print("--auto and --approve-auto only work together with --birthdays-today.")
        return 2
    now = datetime.now()
    campaign = f"{args.campaign}-{now.year}" if args.birthdays_today else args.campaign
    rows = sp.read_contacts(Path(args.contacts))
    bday_note = ""
    if args.birthdays_today:
        todays, readable, bad = filter_birthdays(rows, now.date())
        bday_note = (f"Birthday mode: {len(todays)} birthday(s) today ({now:%b %d}); {len(readable)} people have a "
                     f"readable birthday; {bad} have none or an unreadable one (they are never texted in this mode).")
        rows = readable if args.approve_auto else todays
    plan = build_plan(rows, template, args.country_code,
                      sp.load_suppression(args.suppression, args.country_code),
                      load_done_phones(log_path, campaign), args.fallback, args.require_consent)
    ready, rej = plan["ready"], plan["rejected"]
    if args.status:
        st = log_stats(log_path, campaign)
        total = len(ready) + plan["already_done"]
        print(f"Campaign '{campaign}': {st['submitted']} of {total} submitted, {len(ready)} still to go, "
              f"{st['failed']} failed attempts. Last activity: {st['last'] or 'none yet'}.")
        print(f"Send window {window[0]:02d}:00-{window[1]:02d}:00; it is {datetime.now():%a %I:%M %p} on this phone now.")
        return 0
    interval = max(args.interval, MIN_INTERVAL)
    this_run = min(len(ready), args.max_per_run) if args.max_per_run else len(ready)

    if bday_note:
        print("\n" + bday_note)
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
    linked = [i for i in ready if re.search(r"https?://|www\.", i["message"], re.I)]
    if linked:
        print(f"Note: {len(linked)} message(s) contain a link. Links make carrier spam filters more likely to act; "
              "use your own website or a plain share link, and test with a couple of numbers first.")
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
    approval_path = Path(args.approval_file)
    if args.approve_auto:
        if not ready:
            print("Nobody on the list has a readable birthday and passes the checks, so there is nothing to approve.")
            return 2
        print(f"\nYou are approving this exact message to go out automatically on each person's birthday "
              f"(8am-6pm, one text at a time):\n  {ready[0]['message']}\n"
              "If you change the message or rules, automatic sending stops until you approve again.")
        if input("Type YES to confirm you have permission to text these people: ").strip() != "YES":
            print("Cancelled.")
            return 1
        if input("Type SEND to turn on automatic birthday texts: ").strip() != "SEND":
            print("Cancelled.")
            return 1
        write_approval(approval_path, template, args.campaign, window, args.require_consent, now)
        Path("STOP").unlink(missing_ok=True)
        print(f"Approved. Saved to {approval_path}. Automatic runs may now send this message on birthdays.")
        return 0
    if args.auto:
        if Path("STOP").exists():
            print("STOP file present: automatic birthday texts are paused. Run the birthday setup to turn them back on.")
            return 0
        good, why = approval_ok(approval_path, template, args.campaign, window, args.require_consent)
        if not good:
            print(f"Not sending: {why}.")
            return 3
        if not ready:
            print("No birthdays to text right now.")
            return 0
        if not in_window(now, window):
            print("Outside the send window; skipping (a birthday text a day late is not sent).")
            return 0
        if not shutil.which("termux-sms-send"):
            print("termux-sms-send not found. Install Termux:API (app) and `pkg install termux-api`.")
            return 2
        lock = Path("birthday.lock")
        if not acquire_lock(lock):
            print("Another automatic run is already going; skipping.")
            return 0
        try:
            if shutil.which("termux-wake-lock"):
                subprocess.run(["termux-wake-lock"], check=False)
            res = run(ready, termux_sender(args.sim), time.sleep, log_path, campaign, interval, args.max_per_run,
                      Path("STOP"), window=window, notify=termux_notifier(), same_day_only=True)
        finally:
            lock.unlink(missing_ok=True)
            if shutil.which("termux-wake-unlock"):
                subprocess.run(["termux-wake-unlock"], check=False)
        print(f"Done: {res['submitted']} submitted, {res['failed']} failed."
              + (f" Stopped: {res['stopped']}." if res["stopped"] else ""))
        return 0
    if args.test_to:
        if not ready:
            print("Nothing to test with.")
            return 2
        if not shutil.which("termux-sms-send"):
            print("termux-sms-send not found. Install Termux:API (app) and `pkg install termux-api`.")
            return 2
        print(f"\nTEST: this sends ONE text to {args.test_to} (your own number):\n  {ready[0]['message']}")
        if input("Type SEND to send the test: ").strip() != "SEND":
            print("Cancelled.")
            return 1
        ok, info = send_test(ready, args.test_to, termux_sender(args.sim), log_path, campaign, args.country_code)
        print("Test text submitted. Check that it arrived on that phone." if ok else f"Test failed: {info}")
        return 0 if ok else 1
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
        res = run(ready, termux_sender(args.sim), time.sleep, log_path, campaign,
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
