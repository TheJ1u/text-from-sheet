"""Unit tests. All contacts are fictional. Nothing here can send a message: sms_prep.py contains no
network/SMS code, and test_module_has_no_network_or_send_code proves it by scanning the source."""
import csv
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sms_prep as sp  # noqa: E402

CONFIG = json.loads((ROOT / "data" / "config.example.json").read_text())
TEMPLATES = {k: v for k, v in json.loads((ROOT / "templates" / "templates.json").read_text()).items()
             if not k.startswith("_")}
TODAY = date(2026, 10, 19)


def run_sample(log_state=None, campaign="test-campaign"):
    rows = sp.read_contacts(ROOT / "data" / "sample_contacts.csv")
    supp = sp.load_suppression(ROOT / "data" / "suppression_list.csv")
    return sp.process(rows, CONFIG, TEMPLATES, supp, log_state or {}, campaign, today=TODAY)


def reasons_for(res, first_name):
    return [r["reasons"] for r in res.rejected if r["name"].startswith(first_name)]


class PhoneTests(unittest.TestCase):
    def test_formats_normalize_to_e164(self):
        for raw in ["+1 (801) 555-0101", "801-555-0101", "8015550101", "1-801-555-0101", "(801) 555 0101"]:
            self.assertEqual(sp.normalize_phone(raw), ("+18015550101", None), raw)

    def test_international_numbers_keep_country_code(self):
        self.assertEqual(sp.normalize_phone("+44 20 7946 0958"), ("+442079460958", None))
        self.assertEqual(sp.normalize_phone("0044 20 7946 0958"), ("+442079460958", None))

    def test_bad_numbers_rejected_not_guessed(self):
        cases = {
            "": "missing_phone",
            "555-0108": "phone_needs_country_code",
            "1.80155501E+10": "phone_scientific_notation",
            "801-555-0101 x12": "phone_has_extension",
            "801-CALL-NOW": "phone_has_letters",
            "+1 (011) 555-0101": "phone_invalid_nanp",
            "+123": "phone_bad_length",
            "442079460958": "phone_needs_country_code",
        }
        for raw, err in cases.items():
            self.assertEqual(sp.normalize_phone(raw), (None, err), raw)


class SampleFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = run_sample()

    def test_totals(self):
        self.assertEqual(len(self.res.queue), 5)
        self.assertEqual(len(self.res.rejected), 10)

    def test_expected_queue_members(self):
        self.assertEqual([q["first_name"] for q in self.res.queue],
                         ["Ava", "Ben", "Chloe", "Daniel", "Kara"])

    def test_no_consent_rejected(self):
        self.assertIn("no_affirmative_consent", reasons_for(self.res, "Eva")[0])

    def test_opt_out_and_suppression(self):
        self.assertIn("opted_out", reasons_for(self.res, "Frank")[0])
        self.assertIn("on_suppression_list", reasons_for(self.res, "Grace")[0])

    def test_duplicate_detected_first_kept(self):
        self.assertIn("duplicate_phone_in_file", " ".join(reasons_for(self.res, "Ava")))
        self.assertEqual(sum(1 for q in self.res.queue if q["first_name"] == "Ava"), 1)

    def test_bad_phone_rows(self):
        self.assertIn("phone_needs_country_code", reasons_for(self.res, "Henry")[0])
        self.assertIn("phone_scientific_notation", reasons_for(self.res, "Isla")[0])

    def test_sensitive_medicare_id_blocked(self):
        self.assertIn("sensitive_medicare_id", reasons_for(self.res, "Jack")[0])

    def test_status_sent_not_requeued(self):
        self.assertIn("status_already_processed", reasons_for(self.res, "Liam")[0])

    def test_marketing_needs_consent_date_and_source(self):
        self.assertIn("marketing_needs_valid_consent_date", reasons_for(self.res, "Mia")[0])

    def test_missing_first_name(self):
        self.assertIn("missing_first_name", reasons_for(self.res, "Wright")[0])

    def test_marketing_and_risky_claims_flagged_for_review(self):
        by_name = {q["first_name"]: q for q in self.res.queue}
        self.assertEqual(by_name["Chloe"]["needs_review"], "yes")      # marketing event invite
        self.assertIn("marketing_content", by_name["Chloe"]["review_reasons"])
        self.assertEqual(by_name["Kara"]["needs_review"], "yes")       # "guaranteed", "save", "$"
        self.assertIn("claims_or_promotional_language", by_name["Kara"]["review_reasons"])
        self.assertEqual(by_name["Ava"]["needs_review"], "no")
        self.assertEqual(by_name["Ben"]["needs_review"], "no")

    def test_rendered_messages(self):
        by_name = {q["first_name"]: q for q in self.res.queue}
        self.assertEqual(
            by_name["Ava"]["message"],
            "Hi Ava, this is a reminder of your appointment with Jordan Jenkins at Jenkins Insurance "
            "and Retirement on Oct 24 at 2:30 PM. Reply to confirm or reschedule.")
        self.assertTrue(all("{" not in q["message"] for q in self.res.queue))
        self.assertTrue(all("opt out" not in q["message"].lower() for q in self.res.queue))
        self.assertEqual(by_name["Daniel"]["phone"], "+442079460958")

    def test_notes_never_in_messages(self):
        for q in self.res.queue:
            self.assertNotIn("Fictional test contact", q["message"])
            self.assertNotIn("Risky marketing claim", q["message"])


class ConsentRulesTests(unittest.TestCase):
    def _one(self, **over):
        row = {"first_name": "Test", "last_name": "User", "phone": "801-555-0199", "consent": "yes",
               "consent_date": "2026-08-01", "consent_source": "Web form", "message_type": "service",
               "template": "client_followup", "status": "", "opt_out": "", "message": ""}
        row.update(over)
        return sp.process([(2, row, False)], CONFIG, TEMPLATES, set(), {}, "c", today=TODAY)

    def test_blank_or_unknown_consent_rejected(self):
        for val in ["", "maybe", "no", "pending", "unknown"]:
            self.assertEqual(len(self._one(consent=val).queue), 0, val)

    def test_service_does_not_need_consent_date_but_marketing_does(self):
        self.assertEqual(len(self._one(consent_date="", consent_source="").queue), 1)
        self.assertEqual(len(self._one(message_type="marketing", consent_date="").queue), 0)

    def test_blank_message_type_defaults_to_marketing(self):
        res = self._one(message_type="", consent_date="")
        self.assertEqual(len(res.queue), 0)

    def test_event_invitation_cannot_be_downgraded_to_service(self):
        res = self._one(template="event_invitation", message_type="service", consent_date="",
                        event_name="Workshop", event_date="Nov 6")
        self.assertEqual(len(res.queue), 0)  # still marketing -> needs consent date

    def test_future_consent_date_rejected(self):
        res = self._one(message_type="marketing", consent_date="2027-01-01")
        self.assertIn("consent_date_in_future", res.rejected[0]["reasons"])

    def test_message_conflicting_with_template_rejected(self):
        res = self._one(message="Hello there", template="appointment_reminder")
        self.assertIn("message_conflicts_with_template", res.rejected[0]["reasons"])

    def test_missing_template_field_rejects_instead_of_inventing(self):
        res = self._one(template="appointment_reminder", appointment_date="", appointment_time="")
        self.assertIn("missing_field:appointment_date", res.rejected[0]["reasons"])

    def test_extra_columns_from_unquoted_commas_rejected(self):
        row = {"first_name": "A", "phone": "801-555-0199", "consent": "yes", "template": "client_followup"}
        res = sp.process([(2, row, True)], CONFIG, TEMPLATES, set(), {}, "c", today=TODAY)
        self.assertIn("malformed_row", res.rejected[0]["reasons"])


class ResumeTests(unittest.TestCase):
    def test_terminal_statuses_not_requeued(self):
        first = run_sample()
        key = first.queue[0]["recipient_key"]
        for status in ["sent_action_completed", "skipped", "blocked"]:
            res = run_sample({key: status})
            self.assertNotIn(key, [q["recipient_key"] for q in res.queue], status)
            self.assertEqual(len(res.skipped_done), 1)
            self.assertEqual(len(res.queue), 4)

    def test_failed_and_canceled_are_retryable(self):
        key = run_sample().queue[0]["recipient_key"]
        for status in ["failed", "canceled", "queued", "edited"]:
            self.assertEqual(len(run_sample({key: status}).queue), 5, status)

    def test_approved_without_outcome_is_held_for_manual_check(self):
        key = run_sample().queue[0]["recipient_key"]
        res = run_sample({key: "approved"})
        self.assertEqual(len(res.queue), 4)
        self.assertEqual(len(res.needs_check), 1)

    def test_other_campaign_not_affected(self):
        key = run_sample(campaign="old").queue[0]["recipient_key"]
        self.assertEqual(len(run_sample({key: "sent_action_completed"}, campaign="new").queue), 5)

    def test_log_file_roundtrip_latest_status_wins(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.csv"
            with open(p, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=sp.LOG_FIELDS)
                w.writeheader()
                w.writerow({"recipient_key": "k1", "status": "failed"})
                w.writerow({"recipient_key": "k1", "status": "sent_action_completed"})
                w.writerow({"recipient_key": "k2", "status": "sent_action_completed"})
                w.writerow({"recipient_key": "k2", "status": "failed"})
            st = sp.load_log_state(p)
            self.assertEqual(st["k1"], "sent_action_completed")
            self.assertEqual(st["k2"], "failed")
            self.assertEqual(sp.load_log_state(Path(d) / "missing.csv"), {})


class SensitiveAndAiTests(unittest.TestCase):
    def test_sensitive_patterns(self):
        self.assertIn("sensitive_ssn", sp.find_sensitive("SSN 123-45-6789"))
        self.assertIn("sensitive_medicare_id", sp.find_sensitive("MBI 1EG4-TE5-MK73"))
        self.assertIn("sensitive_medicare_id", sp.find_sensitive("MBI 1EG4TE5MK73"))
        self.assertIn("sensitive_card_or_account_number", sp.find_sensitive("card 4111 1111 1111 1111"))
        self.assertIn("sensitive_health_or_financial_term", sp.find_sensitive("your diagnosis"))
        self.assertEqual(sp.find_sensitive("Hi Ava, appointment Oct 24 at 2:30 PM."), [])

    def test_ai_payload_is_minimal(self):
        q = run_sample().queue[0]
        payload = sp.ai_minimal_payload(q["message"], q["first_name"])
        self.assertEqual(set(payload), {"first_name", "draft"})
        blob = json.dumps(payload)
        self.assertNotIn(q["phone"], blob)
        self.assertNotIn("Martinez", blob)
        self.assertNotIn("Fictional test contact", blob)

    def test_ai_guard(self):
        draft = "Hi Ava, reminder for Oct 24 at 2:30 PM."
        ok, _ = sp.ai_output_guard(draft, "Hi Ava! Quick reminder for Oct 24 at 2:30 PM.")
        self.assertTrue(ok)
        for bad, code in [
            ("Hi Ava, reminder for Oct 24 at 3:30 PM.", "introduced_numbers"),
            ("Hi Ava, reminder Oct 24 at 2:30 PM. Save $50!", "introduced_money"),
            ("Hi Ava, Oct 24 at 2:30 PM. Save $50!", "introduced_money"),
            ("Hi Ava, Oct 24 at 2:30 PM. " + "x" * 400, "too_long"),
            ("", "empty_output"),
        ]:
            ok, problems = sp.ai_output_guard(draft, bad)
            self.assertFalse(ok, bad)
            self.assertIn(code, problems)


class SafetyTests(unittest.TestCase):
    def test_module_has_no_network_or_send_code(self):
        src = (ROOT / "tools" / "sms_prep.py").read_text()
        for banned in [r"\bimport (socket|urllib|requests|http|smtplib|subprocess|ssl)\b",
                       r"\bfrom (urllib|http|requests|subprocess) import", r"\bos\.system\b", r"\bPopen\b"]:
            self.assertIsNone(re.search(banned, src), banned)

    def test_no_secrets_in_repo(self):
        pat = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{16,}", re.I)
        for p in ROOT.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".md", ".json", ".csv", ".txt"} and p.name != "test_sms_prep.py":
                self.assertIsNone(pat.search(p.read_text(errors="ignore")), str(p))

    def test_cli_writes_files_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as d:
            rc = sp.main(["check", str(ROOT / "data" / "sample_contacts.csv"),
                          "--suppression", str(ROOT / "data" / "suppression_list.csv"),
                          "--campaign", "cli-test", "--out", d])
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["queue.csv", "rejected.csv"])
            with open(Path(d) / "queue.csv", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 5)

    def test_xlsx_input_matches_csv(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            with open(ROOT / "data" / "sample_contacts.csv", newline="") as f:
                for row in csv.reader(f):
                    ws.append(row)
            wb.save(p)
            rows = sp.read_contacts(p)
            supp = sp.load_suppression(ROOT / "data" / "suppression_list.csv")
            res = sp.process(rows, CONFIG, TEMPLATES, supp, {}, "x", today=TODAY)
            self.assertEqual([q["phone"] for q in res.queue], [q["phone"] for q in run_sample().queue])


if __name__ == "__main__":
    unittest.main(verbosity=2)
