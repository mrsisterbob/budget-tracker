"""Flexible bank-statement CSV parser.

Built generic on purpose: Huntington's exact export column names weren't available to build
against directly, so this auto-detects common header variants (Date/Posted Date/Transaction
Date, Description/Memo/Payee, Amount, or a split Debit/Credit pair) rather than hardcoding one
bank's schema. If Huntington's real export uses different headers than what's recognized here,
add them to the *_HEADER_ALIASES lists below - no other code needs to change.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

DATE_HEADER_ALIASES = ["date", "posted date", "transaction date", "posting date"]
DESCRIPTION_HEADER_ALIASES = ["description", "memo", "payee", "transaction description", "details"]
AMOUNT_HEADER_ALIASES = ["amount", "transaction amount"]
DEBIT_HEADER_ALIASES = ["debit", "withdrawal", "debit amount"]
CREDIT_HEADER_ALIASES = ["credit", "deposit", "credit amount"]

# Common bank date formats, tried in order until one parses.
DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y"]


class CsvImportError(ValueError):
    """Raised when the CSV doesn't contain a recognizable set of columns."""


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower()


def _find_column(headers_normalized: list[str], aliases: list[str]) -> int | None:
    for alias in aliases:
        if alias in headers_normalized:
            return headers_normalized.index(alias)
    return None


def _parse_date(raw: str) -> str:
    raw = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise CsvImportError(f"Unrecognized date format: {raw!r}")


def _parse_amount(raw: str) -> float:
    cleaned = (raw or "").replace("$", "").replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]  # some exports wrap negatives in parens
    return float(cleaned) if cleaned else 0.0


def parse_bank_csv(file_bytes: bytes) -> list[dict]:
    """Returns a list of {"date": iso_str, "description": str, "amount": float} dicts.
    amount is signed: negative = money out, positive = money in - matching how a signed
    single-Amount-column export normally works, and normalized to that convention even when
    the source file uses separate Debit/Credit columns instead.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")  # utf-8-sig strips a BOM if present
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise CsvImportError("CSV file is empty.")

    headers_raw = rows[0]
    headers_normalized = [_normalize_header(h) for h in headers_raw]

    date_idx = _find_column(headers_normalized, DATE_HEADER_ALIASES)
    desc_idx = _find_column(headers_normalized, DESCRIPTION_HEADER_ALIASES)
    amount_idx = _find_column(headers_normalized, AMOUNT_HEADER_ALIASES)
    debit_idx = _find_column(headers_normalized, DEBIT_HEADER_ALIASES)
    credit_idx = _find_column(headers_normalized, CREDIT_HEADER_ALIASES)

    if date_idx is None or desc_idx is None:
        raise CsvImportError(
            f"Could not find date/description columns in headers: {headers_raw}. "
            "Add this bank's header names to csv_importer.py's alias lists."
        )
    if amount_idx is None and (debit_idx is None or credit_idx is None):
        raise CsvImportError(
            f"Could not find an amount column (or debit+credit pair) in headers: {headers_raw}. "
            "Add this bank's header names to csv_importer.py's alias lists."
        )

    transactions = []
    for row_num, row in enumerate(rows[1:], start=2):
        if not row or all(not cell.strip() for cell in row):
            continue  # skip blank trailing rows, common in bank exports
        try:
            date_iso = _parse_date(row[date_idx])
            description = row[desc_idx].strip()
            if amount_idx is not None:
                amount = _parse_amount(row[amount_idx])
            else:
                debit = _parse_amount(row[debit_idx]) if row[debit_idx].strip() else 0.0
                credit = _parse_amount(row[credit_idx]) if row[credit_idx].strip() else 0.0
                amount = credit - abs(debit)
            transactions.append({"date": date_iso, "description": description, "amount": amount})
        except (CsvImportError, IndexError, ValueError) as e:
            logging.warning(f"Skipping unparseable CSV row {row_num}: {row} ({e})")
            continue

    if not transactions:
        raise CsvImportError("No valid transaction rows found in this CSV.")
    return transactions
