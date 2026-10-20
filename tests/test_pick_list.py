"""Tests for choosing a list from the phone's file picker (Excel or CSV). Fictional numbers only."""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "android"))
import pick_list as pl  # noqa: E402
import send_slow as ss  # noqa: E402


class PickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.dst = self.d / "list.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def run_pick(self, picked):
        return pl.main([str(picked), str(self.dst)])

    def test_excel_file_with_number_cells_and_dates(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["First Name", "Phone", "Birthday"])
        ws.append(["Ava", 8015550101, datetime(1948, 3, 14)])     # Excel stores phone as a number
        ws.append(["José", "(801) 555-0102", "07/04/1950"])
        x = self.d / "picked"
        wb.save(x)
        self.assertEqual(pl.kind_of(x), "xlsx")
        self.assertEqual(self.run_pick(x), 0)
        text = self.dst.read_text(encoding="utf-8")
        self.assertIn("Ava,8015550101,1948-03-14", text)
        self.assertIn("José", text)
        self.assertEqual(ss.parse_birthday("1948-03-14"), (3, 14))

    def test_csv_from_excel_windows_encoding_and_semicolons(self):
        p = self.d / "picked"
        p.write_bytes("First Name;Phone\nJos\xe9;801-555-0101\n".encode("cp1252"))
        self.assertEqual(self.run_pick(p), 0)
        self.assertEqual(self.dst.read_bytes().decode("utf-8"), "First Name,Phone\r\nJosé,801-555-0101\r\n")

    def test_old_xls_pdf_and_empty_are_refused_and_old_list_kept(self):
        self.dst.write_text("Phone\n801-555-0199\n")
        for content in [b"\xd0\xcf\x11\xe0rest", b"%PDF-1.4 ...", b"", b"Phone\n"]:
            p = self.d / "picked"
            p.write_bytes(content)
            self.assertEqual(self.run_pick(p), 1, content[:8])
            self.assertEqual(self.dst.read_text(), "Phone\n801-555-0199\n")

    def test_no_phone_column_is_refused_with_column_names(self):
        import io, contextlib
        self.dst.write_text("Phone\n801-555-0199\n")
        p = self.d / "picked"
        p.write_text("Name,Email\nAva,a@example.com\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(self.run_pick(p), 1)
        self.assertIn("couldn't find a phone column", buf.getvalue())
        self.assertIn("email", buf.getvalue())
        self.assertEqual(self.dst.read_text(), "Phone\n801-555-0199\n")
        self.assertFalse((self.d / "list.csv.new").exists())

    def test_no_usable_numbers_is_refused(self):
        p = self.d / "picked"
        p.write_text("Phone\n555-0108\n")
        self.assertEqual(self.run_pick(p), 1)
        self.assertFalse(self.dst.exists())

    def test_previous_list_is_backed_up(self):
        self.dst.write_text("Phone\n801-555-0199\n")
        p = self.d / "picked"
        p.write_text("First Name,Phone\nAva,801-555-0101\n")
        self.assertEqual(self.run_pick(p), 0)
        self.assertEqual((self.d / "list.prev.csv").read_text(), "Phone\n801-555-0199\n")


class PlainReasonTests(unittest.TestCase):
    def test_codes_become_words(self):
        self.assertEqual(ss.plain_reason("on_suppression_list"), "on your do-not-text list")
        self.assertIn("area code", ss.plain_reason("phone_needs_country_code"))
        self.assertIn("blank first_name", ss.plain_reason("missing_field:first_name"))
        self.assertIn("sensitive info (ssn)", ss.plain_reason("sensitive_ssn"))
        self.assertEqual(ss.plain_reason("something_new"), "something new")


if __name__ == "__main__":
    unittest.main(verbosity=2)
