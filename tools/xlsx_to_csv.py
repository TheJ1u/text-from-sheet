#!/usr/bin/env python3
"""Convert the first sheet of an .xlsx to a clean UTF-8 CSV for the Shortcut.

Why: Shortcuts reads CSV text natively but not .xlsx. Excel also tends to damage phone numbers
(drops '+', converts long digits to scientific notation). This keeps every cell as plain text and
refuses to guess when a cell looks damaged.

  python3 tools/xlsx_to_csv.py contacts.xlsx contacts.csv
"""
import csv
import sys

import openpyxl


def cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def main(src: str, dst: str) -> int:
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    n = 0
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        for row in ws.iter_rows(values_only=True):
            vals = [cell_text(v) for v in row]
            if any(vals):
                w.writerow(vals)
                n += 1
    print(f"Wrote {n} rows (including header) to {dst}")
    print("Note: the iPhone Shortcut needs commas inside fields avoided; run sms_prep.py check to lint.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
