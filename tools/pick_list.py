#!/usr/bin/env python3
"""pick_list.py - turn the file chosen in the phone's file picker into the tool's list.csv.

  python3 tools/pick_list.py <picked-file> list.csv

Accepts an Excel workbook (.xlsx, first sheet) or a CSV (comma, semicolon or tab; UTF-8 or Excel's
Windows encoding). Old .xls files and anything else are refused with a plain explanation. The new list
only replaces the old one if it has a phone column and at least one usable number; the previous list
is kept as list.prev.csv.
"""
from __future__ import annotations

import csv
import io
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sms_prep as sp  # noqa: E402

XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = b"\xd0\xcf\x11\xe0"


def kind_of(path: Path) -> str:
    head = path.read_bytes()[:8]
    if head.startswith(XLSX_MAGIC):
        try:
            with zipfile.ZipFile(path) as z:
                return "xlsx" if any(n.startswith("xl/") for n in z.namelist()) else "zip"
        except zipfile.BadZipFile:
            return "unknown"
    if head.startswith(XLS_MAGIC):
        return "xls"
    if head.startswith(b"%PDF"):
        return "pdf"
    sample = path.read_bytes()[:4096]
    if b"\x00" in sample:
        return "unknown"
    return "csv"


def cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if hasattr(v, "strftime"):                      # Excel dates -> 1948-03-14
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def rows_from_xlsx(path: Path) -> list:
    try:
        import openpyxl
    except ImportError:
        raise SystemExit("Reading Excel files needs one more piece. In Termux, paste:  pip install openpyxl")
    # Loaded from bytes: the picked file has no .xlsx name, and openpyxl refuses unknown file names.
    wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    return [[cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]


def rows_from_csv(path: Path) -> list:
    text = sp.read_text_tolerant(path)
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=sp.sniff_delimiter(text)))


def summarize(csv_path: Path, cc="1") -> dict:
    rows = sp.read_contacts(csv_path)
    headers = set(rows[0][1].keys()) if rows else set()
    good = sum(1 for _, r, _ in rows if sp.normalize_phone(r.get("phone", ""), cc)[0])
    names = sum(1 for _, r, _ in rows if r.get("first_name", "").strip())
    bday = any(k in headers for k in ("birthday", "birth date", "birthdate", "dob", "date of birth", "bday"))
    return {"rows": len(rows), "usable": good, "has_phone_col": "phone" in headers,
            "has_first_name": names > 0, "has_birthday": bday, "headers": sorted(headers)}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(__doc__)
        return 2
    src, dst = Path(argv[0]), Path(argv[1])
    if not src.exists() or src.stat().st_size == 0:
        print("No file was chosen (or it was empty). Nothing changed.")
        return 1
    kind = kind_of(src)
    if kind == "xls":
        print("That's an old Excel file (.xls). In Excel or Google Sheets, save it as .xlsx or CSV, then choose it again.")
        return 1
    if kind != "xlsx" and kind != "csv":
        print("That isn't a spreadsheet. Choose your Excel (.xlsx) or CSV list. Nothing changed.")
        return 1
    rows = rows_from_xlsx(src) if kind == "xlsx" else rows_from_csv(src)
    rows = [r for r in rows if any(str(v).strip() for v in r)]
    if len(rows) < 2:
        print("That file has no people in it (only a header or nothing). Nothing changed.")
        return 1
    tmp = dst.with_name(dst.name + ".new")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    s = summarize(tmp)
    if not s["has_phone_col"]:
        tmp.unlink()
        print("I couldn't find a phone column. Name one column exactly 'Phone' and choose the file again.")
        print("Columns I found: " + ", ".join(s["headers"]))
        return 1
    if s["usable"] == 0:
        tmp.unlink()
        print("The Phone column has no usable numbers (they need an area code). Nothing changed.")
        return 1
    if dst.exists():
        shutil.copyfile(dst, dst.with_name("list.prev.csv"))
    tmp.replace(dst)
    print(f"Got it: {s['rows']} people, {s['usable']} with a usable phone number "
          f"({'Excel file' if kind == 'xlsx' else 'CSV file'}).")
    if not s["has_first_name"]:
        print("Note: no First Name column, so don't use {first_name} in your message.")
    if s["has_birthday"]:
        print("Birthday column found (for Text-9-Birthday-setup).")
    print("This is now your list. Tap Text-1-Preview next. (Your previous list was saved as list.prev.csv.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
