"""Birthday automation tests. Fake phone commands and a fake clock; nothing is ever really sent."""
import os
import stat
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android"))
sys.path.insert(0, str(ROOT / "tools"))
import send_slow as ss  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_formats(self):
        for raw, want in [("03/14", (3, 14)), ("3/14/1948", (3, 14)), ("03-14-48", (3, 14)), ("1948-03-14", (3, 14)),
                          ("1948-03-14 00:00:00", (3, 14)), ("March 14", (3, 14)), ("Mar 14, 1948", (3, 14)),
                          ("mar 14th", (3, 14)), ("02/29/1952", (2, 29))]:
            self.assertEqual(ss.parse_birthday(raw), want, raw)

    def test_bad_values_are_none_not_guessed(self):
        for raw in ["", "  ", "13/40", "14/03/1948", "Smarch 4", "tomorrow", "02/30", "0/5"]:
            self.assertIsNone(ss.parse_birthday(raw), raw)

    def test_today_and_leap_day(self):
        self.assertTrue(ss.is_birthday_today((3, 14), date(2027, 3, 14)))
        self.assertFalse(ss.is_birthday_today((3, 14), date(2027, 3, 15)))
        self.assertFalse(ss.is_birthday_today(None, date(2027, 3, 14)))
        self.assertTrue(ss.is_birthday_today((2, 29), date(2027, 2, 28)))      # not a leap year: Feb 28
        self.assertFalse(ss.is_birthday_today((2, 29), date(2028, 2, 28)))     # leap year: real Feb 29
        self.assertTrue(ss.is_birthday_today((2, 29), date(2028, 2, 29)))

    def test_filter_counts_unreadable(self):
        rows = [(2, {"phone": "1", "birthday": "03/14"}, False), (3, {"phone": "2", "dob": "bad"}, False),
                (4, {"phone": "3"}, False), (5, {"phone": "4", "birthday": "07/01"}, False)]
        today, readable, bad = ss.filter_birthdays(rows, date(2027, 3, 14))
        self.assertEqual([r[0] for r in today], [2])
        self.assertEqual(len(readable), 2)
        self.assertEqual(bad, 2)


class ApprovalTests(unittest.TestCase):
    def test_approval_matches_only_the_exact_message_and_rules(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.json"
            ok, why = ss.approval_ok(f, "Hi {first_name}", "birthday", (8, 18), False)
            self.assertFalse(ok)
            ss.write_approval(f, "Hi {first_name}", "birthday", (8, 18), False, datetime(2026, 10, 19, 21, 0))
            self.assertTrue(ss.approval_ok(f, "Hi {first_name}", "birthday", (8, 18), False)[0])
            self.assertFalse(ss.approval_ok(f, "Hi {first_name}!", "birthday", (8, 18), False)[0])
            self.assertFalse(ss.approval_ok(f, "Hi {first_name}", "birthday", (7, 18), False)[0])
            self.assertFalse(ss.approval_ok(f, "Hi {first_name}", "birthday", (8, 18), True)[0])
            f.write_text("not json")
            self.assertFalse(ss.approval_ok(f, "Hi {first_name}", "birthday", (8, 18), False)[0])

    def test_lock_blocks_a_second_live_run_but_not_a_dead_one(self):
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "l"
            self.assertTrue(ss.acquire_lock(lock))
            self.assertFalse(ss.acquire_lock(lock))            # our own pid is alive
            lock.write_text("999999999")                          # a pid that does not exist
            self.assertTrue(ss.acquire_lock(lock))


class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


class SameDayTests(unittest.TestCase):
    def test_run_stops_when_the_day_ends(self):
        clock = Clock(datetime(2026, 10, 19, 23, 59, 0))
        sent = []
        with tempfile.TemporaryDirectory() as d:
            items = [{"phone": "+18015550101", "name": "A", "message": "hi", "tz": ""},
                     {"phone": "+18015550102", "name": "B", "message": "hi", "tz": ""}]
            res = ss.run(items, lambda p, t: (sent.append(p) or True, "ok"), clock.sleep, Path(d) / "l.csv", "c", 65, 0,
                         Path(d) / "STOP", out=lambda *_: None, now_fn=clock.now, window=(0, 24), same_day_only=True)
        self.assertEqual(sent, ["+18015550101"])
        self.assertIn("day ended", res["stopped"])


class AutoFlowTests(unittest.TestCase):
    """main() end to end with a fake termux-sms-send on PATH."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.d)
        bin_ = self.d / "bin"
        bin_.mkdir()
        self.sent_log = self.d / "sent.txt"
        fake = bin_ / "termux-sms-send"
        fake.write_text(f'#!/bin/sh\necho "$@" >> {self.sent_log}\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.env = mock.patch.dict(os.environ, {"PATH": f"{bin_}:{os.environ['PATH']}"})
        self.env.start()
        t = date.today()
        (self.d / "list.csv").write_text(
            "First Name,Phone,Birthday\n"
            f"Ava,801-555-0101,{t.month:02d}/{t.day:02d}/1950\n"
            "Ben,801-555-0102,01/01/1950\n" if (t.month, t.day) != (1, 1) else
            "First Name,Phone,Birthday\nAva,801-555-0101,01/01/1950\nBen,801-555-0102,07/04/1950\n")
        (self.d / "msg.txt").write_text("Happy birthday, {first_name}!\n")
        self.base = [str(self.d / "list.csv"), "--message-file", str(self.d / "msg.txt"), "--campaign", "birthday",
                     "--birthdays-today", "--window-start", "0", "--window-end", "24"]

    def tearDown(self):
        self.env.stop()
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def sent(self):
        return self.sent_log.read_text().strip().splitlines() if self.sent_log.exists() else []

    def approve(self, answers=("YES", "SEND")):
        with mock.patch("builtins.input", side_effect=list(answers)):
            return ss.main(self.base + ["--approve-auto"])

    def test_auto_refuses_without_approval(self):
        self.assertEqual(ss.main(self.base + ["--auto"]), 3)
        self.assertEqual(self.sent(), [])

    def test_wrong_typed_answers_do_not_approve(self):
        self.assertEqual(self.approve(("yes", "SEND")), 1)
        self.assertFalse((self.d / "auto_approval.json").exists())
        self.assertEqual(self.approve(("YES", "send")), 1)
        self.assertFalse((self.d / "auto_approval.json").exists())

    def test_approved_auto_run_texts_only_todays_birthday_once(self):
        self.assertEqual(self.approve(), 0)
        self.assertEqual(ss.main(self.base + ["--auto"]), 0)
        self.assertEqual(len(self.sent()), 1)
        self.assertIn("+18015550101", self.sent()[0])
        self.assertIn("Happy birthday, Ava!", self.sent()[0])
        self.assertEqual(ss.main(self.base + ["--auto"]), 0)               # the hourly re-run is harmless
        self.assertEqual(len(self.sent()), 1)
        log = (self.d / "send_log.csv").read_text()
        self.assertIn(f"birthday-{date.today().year}", log)
        self.assertNotIn("+18015550102", log)

    def test_changing_the_message_stops_auto_until_reapproved(self):
        self.approve()
        (self.d / "msg.txt").write_text("Happy birthday {first_name}, big day!\n")
        self.assertEqual(ss.main(self.base + ["--auto"]), 3)
        self.assertEqual(self.sent(), [])

    def test_stop_file_pauses_auto(self):
        self.approve()
        (self.d / "STOP").write_text("")
        self.assertEqual(ss.main(self.base + ["--auto"]), 0)
        self.assertEqual(self.sent(), [])

    def test_outside_window_skips_instead_of_sending_late(self):
        h = (datetime.now().hour + 12) % 24
        args = self.base[:-4] + ["--window-start", str(h), "--window-end", str(h + 1)]
        with mock.patch("builtins.input", side_effect=["YES", "SEND"]):
            self.assertEqual(ss.main(args + ["--approve-auto"]), 0)
        self.assertEqual(ss.main(args + ["--auto"]), 0)
        self.assertEqual(self.sent(), [])

    def test_changing_the_send_hours_also_needs_new_approval(self):
        self.approve()
        args = self.base[:-4] + ["--window-start", "9", "--window-end", "17"]
        self.assertEqual(ss.main(args + ["--auto"]), 3)

    def test_auto_only_allowed_with_birthday_mode(self):
        base = [a for a in self.base if a != "--birthdays-today"]
        self.assertEqual(ss.main(base + ["--auto"]), 2)

    def test_do_not_text_list_beats_birthdays(self):
        self.approve()
        (self.d / "dnt.csv").write_text("Phone\n+18015550101\n")
        self.assertEqual(ss.main(self.base + ["--auto", "--suppression", str(self.d / "dnt.csv")]), 0)
        self.assertEqual(self.sent(), [])

    def test_dry_run_shows_birthday_summary_and_sends_nothing(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ss.main(self.base + ["--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("Birthday mode:", buf.getvalue())
        self.assertEqual(self.sent(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
