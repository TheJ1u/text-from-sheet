"""Picture-mode tests. A fake 'open Messages' launcher and fake typed replies; nothing opens or sends."""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android"))
sys.path.insert(0, str(ROOT / "tools"))
import send_picture as spic  # noqa: E402
import send_slow as ss  # noqa: E402


def items(n):
    return [{"phone": f"+1801555{i:04d}", "name": f"P{i}", "message": f"Hi P{i}", "tz": ""} for i in range(n)]


class Launcher:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, phone, text, path, mime):
        self.calls.append((phone, text, str(path), mime))
        return (not self.fail), ("Error: no app" if self.fail else "opened")


class WalkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "log.csv"
        self.pic = Path(self.tmp.name) / "picture.jpg"
        self.pic.write_bytes(b"\xff\xd8fake")

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, ready, replies, launcher=None, now=datetime(2026, 10, 20, 10, 0)):
        launcher = launcher or Launcher()
        it = iter(replies)
        res = spic.walk(ready, launcher, lambda _: next(it), self.log, "flyer", self.pic, "image/jpeg",
                        out=lambda *_: None, now_fn=lambda: now)
        return res, launcher

    def test_enter_marks_sent_s_skips_q_quits(self):
        res, l = self.go(items(4), ["", "s", "", "q"])
        self.assertEqual((res["sent"], res["skipped"]), (2, 1))
        self.assertEqual(res["stopped"], "you quit")
        self.assertEqual(len(l.calls), 4)
        self.assertEqual(l.calls[0][:2], ("+18015550000", "Hi P0"))
        self.assertEqual(ss.load_done_phones(self.log, "flyer"), {"+18015550000", "+18015550002"})

    def test_resume_skips_people_already_sent(self):
        self.go(items(2), ["", "q"])
        done = ss.load_done_phones(self.log, "flyer")
        self.assertEqual(done, {"+18015550000"})

    def test_outside_hours_nothing_opens(self):
        res, l = self.go(items(3), [], now=datetime(2026, 10, 20, 21, 0))
        self.assertEqual(l.calls, [])
        self.assertEqual(res["later"], 3)

    def test_launch_failure_stops_and_logs_nothing(self):
        res, l = self.go(items(3), [""], launcher=Launcher(fail=True))
        self.assertEqual(res["stopped"], "could not open Messages")
        self.assertFalse(self.log.exists())

    def test_log_says_sent_by_you_not_delivered(self):
        self.go(items(1), [""])
        text = self.log.read_text()
        self.assertIn("sent by you in Messages", text)
        self.assertNotIn("delivered", text.replace("delivery_confirmed", ""))


class HelperTests(unittest.TestCase):
    def test_intent_has_number_text_and_picture(self):
        cmd = spic.intent_command("+18015550101", "Hi Ava", Path("/storage/emulated/0/Download/p.jpg"), "image/jpeg")
        self.assertEqual(cmd[:4], ["am", "start", "-a", "android.intent.action.SEND"])
        self.assertIn("+18015550101", cmd)
        self.assertIn("Hi Ava", cmd)
        self.assertIn("file:///storage/emulated/0/Download/p.jpg", cmd)

    def test_mime_and_notes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            jpg, pdf, big = d / "a.jpg", d / "b.pdf", d / "c.png"
            jpg.write_bytes(b"x" * 100)
            pdf.write_bytes(b"x" * 100)
            big.write_bytes(b"x" * 2_000_000)
            self.assertEqual(spic.mime_of(jpg), "image/jpeg")
            self.assertEqual(spic.attachment_notes(jpg, "image/jpeg"), [])
            self.assertIn("PDF", spic.attachment_notes(pdf, spic.mime_of(pdf))[0])
            self.assertIn("Big file", spic.attachment_notes(big, "image/png")[0])
            self.assertEqual(spic.mime_of(d / "x.vcf"), "text/vcard")

    def test_private_files_are_copied_to_shared_storage(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "private" / "pic.JPG"
            src.parent.mkdir()
            src.write_bytes(b"img")
            out = spic.shareable_path(src, d / "shared")
            self.assertEqual(out.read_bytes(), b"img")
            self.assertEqual(out.name, "text-tool-attachment.jpg")


class MainTests(unittest.TestCase):
    def test_dry_run_and_safety_refusals(self):
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "l.csv").write_text("First Name,Phone\nAva,801-555-0101\n")
            (d / "p.jpg").write_bytes(b"img")
            base = [str(d / "l.csv"), "--message", "Hi {first_name}", "--campaign", "f", "--log", str(d / "log.csv")]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(spic.main(base + ["--attach", str(d / "p.jpg"), "--dry-run"]), 0)
                self.assertEqual(spic.main(base + ["--attach", str(d / "missing.jpg")]), 2)
                self.assertEqual(spic.main(base + ["--attach", str(d / "p.jpg"), "--suppression", str(d / "typo.csv")]), 2)
            out = buf.getvalue()
            self.assertIn("[+ p.jpg]", out)
            self.assertIn("Dry run", out)
            self.assertFalse((d / "log.csv").exists())

    def test_wrong_typed_yes_cancels(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "l.csv").write_text("First Name,Phone\nAva,801-555-0101\n")
            (d / "p.jpg").write_bytes(b"img")
            with mock.patch("shutil.which", return_value="/bin/am"), mock.patch("builtins.input", return_value="yes"):
                rc = spic.main([str(d / "l.csv"), "--message", "Hi", "--campaign", "f", "--log", str(d / "log.csv"),
                                "--attach", str(d / "p.jpg")])
            self.assertEqual(rc, 1)
            self.assertFalse((d / "log.csv").exists())

    def test_no_background_send_capability(self):
        src = (ROOT / "android" / "send_picture.py").read_text()
        self.assertNotIn("termux-sms-send", src)
        self.assertNotIn("input tap", src)          # never auto-taps the Send button


if __name__ == "__main__":
    unittest.main(verbosity=2)
