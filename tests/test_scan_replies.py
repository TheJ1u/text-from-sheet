"""Tests for the reply scanner (fake received-text data; touches nothing on a phone)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "android"))
sys.path.insert(0, str(ROOT / "tools"))
import scan_replies as sr  # noqa: E402


class ClassifyTests(unittest.TestCase):
    def test_clear_requests_are_definite(self):
        for body in ["STOP", "Stop.", "stop all", "Unsubscribe", "please remove me from your list",
                     "Do not text me again", "don't contact me", "take me off this list"]:
            self.assertEqual(sr.classify(body), "definite", body)

    def test_ambiguous_replies_are_only_maybe(self):
        for body in ["stop by tomorrow?", "wrong number", "who is this?", "not interested"]:
            self.assertEqual(sr.classify(body), "maybe", body)

    def test_normal_replies_are_ignored(self):
        for body in ["Sounds great, see you Friday", "Yes!", "What time?"]:
            self.assertEqual(sr.classify(body), "", body)


class ScanTests(unittest.TestCase):
    MSGS = [
        {"number": "(801) 555-0101", "body": "STOP", "type": "inbox"},
        {"number": "+18015550102", "body": "stop by tomorrow", "type": "inbox"},
        {"number": "+18015550103", "body": "Sounds good", "type": "inbox"},
        {"number": "+18015559999", "body": "STOP", "type": "inbox"},      # not on the list: ignored
        {"number": "+18015550103", "body": "STOP", "type": "sent"},      # our own text: ignored
        {"number": "22000", "body": "STOP", "type": "inbox"},            # short code: ignored
    ]
    PHONES = {"+18015550101", "+18015550102", "+18015550103"}

    def test_scan_only_flags_listed_inbound_numbers(self):
        d, m = sr.scan(self.MSGS, self.PHONES)
        self.assertEqual(set(d), {"+18015550101"})
        self.assertEqual(set(m), {"+18015550102"})

    def test_main_adds_definite_after_typed_yes_and_never_maybe(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "list.csv").write_text("First Name,Phone\nAva,801-555-0101\nBen,801-555-0102\nCy,801-555-0103\n")
            (t / "m.json").write_text(json.dumps(self.MSGS))
            dnt = t / "dnt.csv"
            with mock.patch("builtins.input", return_value="YES"):
                rc = sr.main([str(t / "list.csv"), "--suppression", str(dnt), "--from-json", str(t / "m.json")])
            self.assertEqual(rc, 0)
            body = dnt.read_text()
            self.assertIn("+18015550101", body)
            self.assertNotIn("+18015550102", body)
            with mock.patch("builtins.input", return_value="no"):
                dnt.unlink()
                rc = sr.main([str(t / "list.csv"), "--suppression", str(dnt), "--from-json", str(t / "m.json")])
            self.assertEqual(rc, 1)
            self.assertFalse(dnt.exists())

    def test_script_has_no_send_capability(self):
        src = (ROOT / "android" / "scan_replies.py").read_text()
        self.assertNotIn("termux-sms-send", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
