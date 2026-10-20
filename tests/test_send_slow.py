"""Tests for android/send_slow.py using a FAKE sender and FAKE sleep. Nothing real is sent and no
test waits on a clock."""
import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android"))
import send_slow as ss  # noqa: E402
import sms_prep as sp  # noqa: E402

CSV_TEXT = """First Name,Last Name,Phone,Event,Opt Out,Consent
Ava,Martinez,+1 801 555 0101,Friday dinner,,yes
Ben,Carter,801-555-0102,Friday dinner,,yes
Ava,Martinez,(801) 555-0101,Friday dinner,,yes
Eva,Lindqvist,801-555-0105,Friday dinner,Yes,yes
Henry,Brooks,555-0108,Friday dinner,,yes
Isla,Fernandez,1.80155501E+10,Friday dinner,,yes
,Wright,801-555-0115,Friday dinner,,yes
Gus,Nolan,801-555-0116,Friday dinner,,
Kara,Singh,801-555-0117,Friday dinner,,yes
"""


def plan_for(template="Hi {first_name}, dinner? ({Event})", csv_text=CSV_TEXT, **kw):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.csv"
        p.write_text(csv_text)
        return ss.build_plan(sp.read_contacts(p), template, **kw)


class Fake:
    def __init__(self, fail_phones=()):
        self.sent, self.fail, self.slept = [], set(fail_phones), 0

    def send(self, phone, text):
        self.sent.append((phone, text))
        return (phone not in self.fail), ("ok" if phone not in self.fail else "no permission")

    def sleep(self, s):
        self.slept += s


class PlanTests(unittest.TestCase):
    def test_plan_filters(self):
        plan = plan_for()
        self.assertEqual([r["phone"] for r in plan["ready"]], ["+18015550101", "+18015550102", "+18015550117"])
        why = {r["name"]: r["reasons"] for r in plan["rejected"]}
        self.assertIn("duplicate_phone", why["Ava Martinez"])
        self.assertIn("opted_out", why["Eva Lindqvist"])
        self.assertIn("phone_needs_country_code", why["Henry Brooks"])
        self.assertIn("phone_scientific_notation", why["Isla Fernandez"])
        self.assertIn("missing_field:first_name", why["Wright"])
        self.assertIn("no_affirmative_consent", why["Gus Nolan"])

    def test_messages_rendered_and_nothing_invented(self):
        plan = plan_for()
        self.assertEqual(plan["ready"][0]["message"], "Hi Ava, dinner? (Friday dinner)")

    def test_fallback_fills_blank_name(self):
        plan = plan_for(fallback="there")
        names = [r["message"] for r in plan["ready"]]
        self.assertIn("Hi there, dinner? (Friday dinner)", names)

    def test_sensitive_text_blocks_everyone(self):
        plan = plan_for(template="Hi {first_name}, SSN 123-45-6789")
        self.assertEqual(plan["ready"], [])

    def test_already_done_skipped(self):
        plan = plan_for(done={"+18015550101"})
        self.assertEqual(plan["already_done"], 1)
        self.assertNotIn("+18015550101", [r["phone"] for r in plan["ready"]])

    def test_unfilled_unknown_field_rejected(self):
        plan = plan_for(template="Hi {first_name} {nope}")
        self.assertEqual(plan["ready"], [])


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "log.csv"
        self.stop = Path(self.tmp.name) / "STOP"
        self.items = [{"phone": f"+1801555{i:04d}", "name": f"P{i}", "message": f"hi {i}"} for i in range(1, 6)]

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, fake, **kw):
        args = dict(ready=self.items, sender=fake.send, sleep=fake.sleep, log_path=self.log, campaign="c",
                    interval=65, max_per_run=0, stop_file=self.stop, out=lambda *_: None, window=(0, 24))
        args.update(kw)
        return ss.run(**args)

    def rows(self):
        with open(self.log, newline="") as f:
            return list(csv.DictReader(f))

    def test_sends_all_with_spacing_and_logs(self):
        f = Fake()
        res = self.go(f)
        self.assertEqual(res["submitted"], 5)
        self.assertEqual(len(f.sent), 5)
        self.assertEqual(f.slept, 65 * 4, "waits between texts, not after the last")
        rows = self.rows()
        self.assertTrue(all(r["status"] == "submitted" and r["delivery_confirmed"] == "unknown" for r in rows))

    def test_interval_cannot_go_below_minimum(self):
        f = Fake()
        self.go(f, interval=5)
        self.assertEqual(f.slept, ss.MIN_INTERVAL * 4)

    def test_no_limit_by_default_sends_400_in_one_run(self):
        f = Fake()
        many = [{"phone": f"+1801{i:07d}", "name": f"P{i}", "message": "hi"} for i in range(5550000, 5550400)]
        res = self.go(f, ready=many)
        self.assertEqual(len(f.sent), 400)
        self.assertEqual(res["submitted"], 400)
        self.assertEqual(res["remaining_in_list"], 0)

    def test_optional_cap_still_works(self):
        f = Fake()
        res = self.go(f, max_per_run=2)
        self.assertEqual(len(f.sent), 2)
        self.assertEqual(res["remaining_in_list"], 3)

    def test_stop_file_halts_immediately(self):
        f = Fake()
        self.stop.write_text("")
        res = self.go(f)
        self.assertEqual(len(f.sent), 0)
        self.assertEqual(res["stopped"], "STOP file found")

    def test_stop_file_created_mid_wait(self):
        f = Fake()
        orig = f.sleep

        def sleep(s):
            orig(s)
            self.stop.write_text("")
        res = self.go(f, sleep=sleep)
        self.assertEqual(len(f.sent), 1)
        self.assertTrue(res["stopped"])

    def test_three_failures_in_a_row_abort(self):
        f = Fake(fail_phones={i["phone"] for i in self.items})
        res = self.go(f)
        self.assertEqual(len(f.sent), 3)
        self.assertIn("failures in a row", res["stopped"])

    def test_resume_after_partial_run(self):
        self.go(Fake(), max_per_run=2)
        done = ss.load_done_phones(self.log, "c")
        self.assertEqual(len(done), 2)
        remaining = [i for i in self.items if i["phone"] not in done]
        f = Fake()
        self.go(f, ready=remaining)
        self.assertEqual(len(f.sent), 3)
        self.assertTrue(not (done & {p for p, _ in f.sent}), "nobody texted twice")

    def test_failed_not_counted_as_done(self):
        f = Fake(fail_phones={self.items[0]["phone"]})
        self.go(f, max_per_run=1)
        self.assertEqual(ss.load_done_phones(self.log, "c"), set())

    def test_done_is_per_campaign(self):
        self.go(Fake(), max_per_run=1)
        self.assertEqual(ss.load_done_phones(self.log, "other"), set())


class NotifyStatusTests(unittest.TestCase):
    def test_notifications_report_progress_and_never_break_sending(self):
        with tempfile.TemporaryDirectory() as d:
            msgs = []
            items = [{"phone": f"+1801555{i:04d}", "name": f"P{i}", "message": "hi"} for i in range(3)]
            f = Fake()
            res = ss.run(items, f.send, f.sleep, Path(d) / "l.csv", "c", 65, 0, Path(d) / "STOP",
                         out=lambda *_: None, window=(0, 24), notify=msgs.append)
            self.assertEqual(res["submitted"], 3)
            self.assertTrue(msgs[-1].startswith("Finished: 3 submitted"))
            self.assertTrue(any("2 of 3 done" in m for m in msgs))

            def boom(_):
                raise RuntimeError("notification app missing")
            f2 = Fake()
            res2 = ss.run(items, f2.send, f2.sleep, Path(d) / "l2.csv", "c", 65, 0, Path(d) / "STOP",
                          out=lambda *_: None, window=(0, 24), notify=boom)
            self.assertEqual(res2["submitted"], 3)

    def test_status_command_reads_log(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "c.csv"
            c.write_text("Phone\n801-555-0101\n801-555-0102\n801-555-0103\n")
            log = Path(d) / "log.csv"
            ss.append_log(log, {"timestamp": "2026-10-19T09:00:00+00:00", "campaign": "x", "phone": "+18015550101",
                                "name": "A", "status": "submitted", "delivery_confirmed": "unknown", "note": "ok", "message": "hi"})
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ss.main([str(c), "--message", "Hi", "--campaign", "x", "--log", str(log), "--status"])
            self.assertEqual(rc, 0)
            self.assertIn("1 of 3 submitted, 2 still to go", buf.getvalue())


class Clock:
    """Fake clock: sleep() advances time, so overnight waits finish instantly in tests."""
    def __init__(self, start):
        self.t = start

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "log.csv"
        self.stop = Path(self.tmp.name) / "STOP"

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, items, start, **kw):
        clock = Clock(start)
        stamps = []
        fake = Fake()

        def send(phone, text):
            stamps.append(clock.now())
            return fake.send(phone, text)
        args = dict(ready=items, sender=send, sleep=clock.sleep, log_path=self.log, campaign="c", interval=65,
                    max_per_run=0, stop_file=self.stop, out=lambda *_: None, now_fn=clock.now, window=(8, 18))
        args.update(kw)
        return ss.run(**args), stamps

    def items(self, n):
        return [{"phone": f"+1801555{i:04d}", "name": f"P{i}", "message": "hi"} for i in range(n)]

    def test_window_helpers(self):
        w = (8, 18)
        self.assertFalse(ss.in_window(datetime(2026, 10, 19, 7, 59), w))
        self.assertTrue(ss.in_window(datetime(2026, 10, 19, 8, 0), w))
        self.assertTrue(ss.in_window(datetime(2026, 10, 19, 17, 59), w))
        self.assertFalse(ss.in_window(datetime(2026, 10, 19, 18, 0), w))
        self.assertEqual(ss.next_window_open(datetime(2026, 10, 19, 20, 0), w), datetime(2026, 10, 20, 8, 0))
        self.assertEqual(ss.next_window_open(datetime(2026, 10, 19, 3, 0), w), datetime(2026, 10, 19, 8, 0))

    def test_never_sends_outside_window_and_resumes_next_morning(self):
        # start at 5:30pm: only ~27 texts fit before 6pm, rest wait until 8am next day
        res, stamps = self.go(self.items(60), datetime(2026, 10, 19, 17, 30))
        self.assertEqual(res["submitted"], 60)
        self.assertTrue(all(8 <= t.hour < 18 for t in stamps), [t for t in stamps if not 8 <= t.hour < 18][:3])
        self.assertTrue(any(t.date() == datetime(2026, 10, 20).date() for t in stamps), "continued next day")
        first_next_day = min(t for t in stamps if t.date() == datetime(2026, 10, 20).date())
        self.assertEqual((first_next_day.hour, first_next_day.minute), (8, 0))

    def test_starting_at_night_waits_until_8am(self):
        res, stamps = self.go(self.items(3), datetime(2026, 10, 19, 22, 0))
        self.assertEqual(stamps[0], datetime(2026, 10, 20, 8, 0))

    def test_gaps_between_texts_respect_interval(self):
        _, stamps = self.go(self.items(5), datetime(2026, 10, 19, 9, 0))
        gaps = {(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])}
        self.assertEqual(gaps, {65.0})

    def test_stop_file_works_while_waiting_overnight(self):
        clock_calls = []

        def stopper(*_):
            clock_calls.append(1)
            if len(clock_calls) == 1:
                self.stop.write_text("")
        res, stamps = self.go(self.items(3), datetime(2026, 10, 19, 22, 0), out=stopper)
        self.assertEqual(stamps, [])
        self.assertEqual(res["stopped"], "STOP file found")

    def test_400_texts_fit_in_one_day_window(self):
        res, stamps = self.go(self.items(400), datetime(2026, 10, 19, 8, 0))
        self.assertEqual(res["submitted"], 400)
        self.assertEqual({t.date() for t in stamps}, {datetime(2026, 10, 19).date()})
        self.assertLess(stamps[-1].hour, 18)

    def test_estimate_text(self):
        self.assertIn("1 day", ss.estimate(400, 65, (8, 18)))
        self.assertIn("2 days", ss.estimate(600, 65, (8, 18)))

    def test_bad_window_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "c.csv"
            c.write_text("Phone\n801-555-0101\n")
            rc = ss.main([str(c), "--message", "Hi", "--campaign", "x", "--window-start", "18", "--window-end", "8", "--dry-run"])
            self.assertEqual(rc, 2)


class SafetyTests(unittest.TestCase):
    def test_dry_run_sends_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "c.csv"
            c.write_text(CSV_TEXT)
            log = Path(d) / "log.csv"
            rc = ss.main([str(c), "--message", "Hi {first_name}", "--campaign", "x", "--log", str(log), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(log.exists())

    def test_no_yes_flag_or_unattended_bypass(self):
        src = (ROOT / "android" / "send_slow.py").read_text()
        self.assertNotIn('"--yes"', src)
        self.assertIn('"SEND"', src)
        self.assertIn('"YES"', src)

    def test_excel_cp1252_csv_with_accents_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "c.csv"
            c.write_bytes("First Name,Phone\nJos\xe9,801-555-0101\n".encode("cp1252"))
            rows = ss.sp.read_contacts(c)
            self.assertEqual(rows[0][1]["first_name"], "Jos\u00e9")

    def test_semicolon_and_tab_delimited_csv(self):
        with tempfile.TemporaryDirectory() as d:
            for delim in (";", "\t"):
                c = Path(d) / "c.csv"
                c.write_text(f"First Name{delim}Phone\nBen{delim}801-555-0103\n", encoding="utf-8")
                self.assertEqual(ss.sp.read_contacts(c)[0][1]["phone"], "801-555-0103")

    def test_missing_suppression_file_refuses_to_run(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "c.csv"
            c.write_text("First Name,Phone\nAva,801-555-0101\n")
            rc = ss.main([str(c), "--message", "Hi", "--campaign", "x", "--suppression", str(Path(d) / "typo.csv"), "--dry-run"])
            self.assertEqual(rc, 2)

    def test_minimum_interval_constant(self):
        self.assertGreaterEqual(ss.MIN_INTERVAL, 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
