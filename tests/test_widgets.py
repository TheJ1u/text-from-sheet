"""Tests for the home-screen button scripts, run against a temp HOME (no phone, nothing sent)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WID = ROOT / "widgets"


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.tool = self.home / "text-tool"
        shutil.copytree(ROOT, self.tool, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"))
        (self.tool / "list.csv").write_text("First Name,Phone\nAva,801-555-0101\nBen,801-555-0102\n")
        self.env = dict(os.environ, HOME=str(self.home), TEXTTOOL_DIR=str(self.tool),
                        SHORTCUTS_DIR=str(self.home / ".shortcuts"))

    def tearDown(self):
        self.tmp.cleanup()

    def sh(self, script, stdin=""):
        return subprocess.run(["bash", str(self.tool / "widgets" / script)], input=stdin, text=True,
                              capture_output=True, env=self.env, timeout=60, cwd=self.home)

    def test_all_scripts_have_valid_syntax(self):
        for f in WID.glob("*.sh"):
            r = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr}")

    def test_install_creates_five_executable_buttons_and_saves_message(self):
        r = self.sh("install_widgets.sh", stdin="Hi {first_name}, dinner Friday?\nfall-dinner\n\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        names = sorted(p.name for p in (self.home / ".shortcuts").iterdir())
        self.assertEqual(names, ["Text-0-Check-setup", "Text-0-Choose-list", "Text-1-Preview", "Text-2-Send-test-to-me", "Text-3-Start", "Text-4-Status", "Text-5-Stop", "Text-6-Change-message", "Text-7-Do-not-text", "Text-8-Check-replies", "Text-9-Birthday-setup", "Text-P-Send-with-picture"])
        for p in (self.home / ".shortcuts").iterdir():
            self.assertTrue(os.access(p, os.X_OK))
            self.assertIn("widgets/", p.read_text())
        self.assertEqual((self.tool / "message.txt").read_text().strip(), "Hi {first_name}, dinner Friday?")
        self.assertEqual((self.tool / "campaign.txt").read_text().strip(), "fall-dinner")

    def test_campaign_name_is_sanitized_and_empty_message_rejected(self):
        self.sh("set_message.sh", stdin="Hello there\nmy batch; rm -rf /\n\n")
        self.assertEqual((self.tool / "campaign.txt").read_text().strip(), "my-batch--rm--rf--")
        before = (self.tool / "message.txt").read_text()
        r = self.sh("set_message.sh", stdin="\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.tool / "message.txt").read_text(), before)

    def test_preview_sends_nothing_and_shows_people(self):
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\n\n")
        r = self.sh("preview.sh", stdin="\n")
        self.assertIn("PREVIEW ONLY", r.stdout)
        self.assertIn("Hi Ava!", r.stdout)
        self.assertIn("Dry run: nothing sent", r.stdout)
        self.assertFalse((self.tool / "send_log.csv").exists())

    def test_status_works_and_stop_creates_flag(self):
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\n\n")
        r = self.sh("status.sh", stdin="\n")
        self.assertIn("0 of 2 submitted", r.stdout)
        self.sh("stop.sh", stdin="\n")
        self.assertTrue((self.tool / "STOP").exists())

    def test_missing_message_or_list_gives_friendly_error(self):
        (self.tool / "list.csv").unlink()
        r = self.sh("preview.sh", stdin="\n")
        self.assertIn("Tap 'Text-6-Change-message'", r.stdout)
        self.assertNotEqual(r.returncode, 0)

    def test_do_not_text_number_is_skipped_in_preview(self):
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\n\n")
        r = self.sh("do_not_text.sh", stdin="(801) 555-0101\n\n")
        self.assertIn("Saved", r.stdout)
        out = self.sh("preview.sh", stdin="\n").stdout
        self.assertIn("on your do-not-text list", out)
        self.assertNotIn("Hi Ava!", out)
        bad = self.sh("do_not_text.sh", stdin="123\n\n")
        self.assertNotEqual(bad.returncode, 0)

    def test_all_sending_scripts_use_the_do_not_text_list(self):
        self.assertIn("--suppression do_not_text.csv", (WID / "common.sh").read_text())
        for f in ("preview.sh", "start.sh", "status.sh", "send_test.sh", "picture_send.sh"):
            self.assertIn("$FLAGS", (WID / f).read_text(), f)

    def test_consent_required_choice_is_saved_and_enforced(self):
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\ny\n\n")
        self.assertTrue((self.tool / "require_consent.txt").exists())
        out = self.sh("preview.sh", stdin="\n").stdout
        self.assertIn("no Consent column", out)
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\nn\n\n")
        self.assertFalse((self.tool / "require_consent.txt").exists())

    def test_check_setup_reports_ok_and_missing_items(self):
        self.sh("set_message.sh", stdin="Hi\nt1\n\n\n")
        r = self.sh("check_setup.sh", stdin="\n")
        self.assertIn("OK       python3", r.stdout)
        self.assertIn("MISSING  Termux:API", r.stdout)   # not on a phone
        self.assertNotEqual(r.returncode, 0)

    def test_test_to_me_needs_a_phone_to_send_and_sends_nothing_here(self):
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\n\n")
        r = self.sh("send_test.sh", stdin="801-555-0199\n\n")
        self.assertIn("termux-sms-send not found", r.stdout)
        self.assertFalse((self.tool / "send_log.csv").exists())

    def _fake_bin(self):
        b = self.home / "fakebin"
        b.mkdir(exist_ok=True)
        cron = self.home / "crontab.txt"
        (b / "crontab").write_text(f'#!/bin/sh\nif [ "$1" = "-l" ]; then cat {cron} 2>/dev/null; else cat > {cron}; fi\n')
        (b / "sv-enable").write_text("#!/bin/sh\nexit 0\n")
        for f in b.iterdir():
            f.chmod(0o755)
        self.env["PATH"] = f"{b}:{self.env['PATH']}"
        return cron

    def test_birthday_setup_saves_message_approves_once_and_installs_timer(self):
        from datetime import date
        t = date.today()
        (self.tool / "list.csv").write_text(f"First Name,Phone,Birthday\nAva,801-555-0101,{t.month:02d}/{t.day:02d}/1950\n")
        cron = self._fake_bin()
        r = self.sh("birthday_setup.sh", stdin="Happy birthday, {first_name}!\nYES\nSEND\n\n")
        self.assertIn("Automatic birthday texts are ON", r.stdout, r.stdout + r.stderr)
        self.assertEqual((self.tool / "birthday_message.txt").read_text().strip(), "Happy birthday, {first_name}!")
        self.assertTrue((self.tool / "auto_approval.json").exists())
        self.assertIn("widgets/birthday_run.sh", cron.read_text())
        self.sh("birthday_setup.sh", stdin="Happy birthday, {first_name}!\nYES\nSEND\n\n")   # run twice
        self.assertEqual(cron.read_text().count("birthday_run.sh"), 1)                          # no duplicate timer

    def test_birthday_setup_without_typed_approval_turns_nothing_on(self):
        from datetime import date
        t = date.today()
        (self.tool / "list.csv").write_text(f"First Name,Phone,Birthday\nAva,801-555-0101,{t.month:02d}/{t.day:02d}/1950\n")
        cron = self._fake_bin()
        r = self.sh("birthday_setup.sh", stdin="Hi {first_name}\nyes\nSEND\n\n")
        self.assertIn("Not turned on", r.stdout)
        self.assertFalse((self.tool / "auto_approval.json").exists())
        self.assertFalse(cron.exists())

    def test_birthday_run_refuses_without_approval_and_logs_why(self):
        from datetime import date
        t = date.today()
        (self.tool / "list.csv").write_text(f"First Name,Phone,Birthday\nAva,801-555-0101,{t.month:02d}/{t.day:02d}/1950\n")
        (self.tool / "birthday_message.txt").write_text("Happy birthday {first_name}\n")
        subprocess.run(["bash", str(self.tool / "widgets" / "birthday_run.sh")], env=self.env, cwd=self.home, timeout=60)
        self.assertIn("Not sending", (self.tool / "birthday_log.txt").read_text())
        self.assertFalse((self.tool / "send_log.csv").exists())

    def test_picture_button_explains_where_to_put_the_picture(self):
        self.sh("set_message.sh", stdin="Hi {first_name}!\nt1\n\n")
        r = self.sh("picture_send.sh", stdin="\n")
        self.assertIn("Save it in Downloads named picture.jpg", r.stdout)
        dl = self.home / "storage" / "downloads"
        dl.mkdir(parents=True)
        (dl / "picture.jpg").write_bytes(b"\xff\xd8fake")
        r = self.sh("picture_send.sh", stdin="\n")
        self.assertIn("Picture/file: picture.jpg", r.stdout)
        self.assertIn("only works inside Termux", r.stdout)       # no Android here, so nothing opens

    def test_choose_list_uses_the_file_picker_result(self):
        b = self.home / "pickbin"
        b.mkdir()
        src = self.home / "from_drive.csv"
        src.write_text("First Name,Phone\nZoe,801-555-0177\n")
        (b / "termux-storage-get").write_text(f'#!/bin/sh\ncp "{src}" "$1"\n')
        (b / "termux-storage-get").chmod(0o755)
        self.env["PATH"] = f"{b}:{self.env['PATH']}"
        r = self.sh("choose_list.sh", stdin="\n")
        self.assertIn("Got it: 1 people, 1 with a usable phone number", r.stdout, r.stdout + r.stderr)
        self.assertIn("Zoe", (self.tool / "list.csv").read_text())
        self.assertFalse((self.tool / ".picked_file").exists())

    def test_choose_list_without_termux_api_explains(self):
        r = self.sh("choose_list.sh", stdin="\n")
        self.assertIn("needs the Termux:API app", r.stdout)

    def test_start_script_never_bypasses_the_typed_approval(self):
        src = (WID / "start.sh").read_text()
        self.assertIn("send_slow.py", src)
        self.assertNotIn("--yes", src)
        self.assertNotIn("echo YES", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
