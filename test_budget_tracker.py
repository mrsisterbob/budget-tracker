"""Unit tests for csv_importer and categorizer - pure logic, no Flask/network required."""
import pytest

from categorizer import categorize_transaction
from csv_importer import CsvImportError, parse_bank_csv

TEST_RULES = {
    "necessary": {"Groceries": ["kroger", "meijer"], "Utilities": ["electric"]},
    "discretionary": {"Dining Out": ["starbucks", "restaurant"]},
    "income": {"Paycheck": ["payroll", "direct deposit"]},
    "uncategorized_bucket": "Uncategorized",
}


def test_categorize_necessary_match():
    result = categorize_transaction("KROGER #123 GROCERY", -45.20, TEST_RULES)
    assert result == {"bucket": "necessary", "category": "Groceries"}


def test_categorize_discretionary_match():
    result = categorize_transaction("STARBUCKS STORE 4521", -6.75, TEST_RULES)
    assert result == {"bucket": "discretionary", "category": "Dining Out"}


def test_categorize_income_match():
    result = categorize_transaction("PAYROLL DEPOSIT ACME CORP", 2000.00, TEST_RULES)
    assert result == {"bucket": "income", "category": "Paycheck"}


def test_categorize_unmatched_negative_falls_to_uncategorized():
    result = categorize_transaction("SOME RANDOM MERCHANT", -12.00, TEST_RULES)
    assert result == {"bucket": "uncategorized", "category": "Uncategorized"}


def test_categorize_unmatched_positive_assumed_income():
    result = categorize_transaction("UNKNOWN DEPOSIT SOURCE", 500.00, TEST_RULES)
    assert result["bucket"] == "income"


def test_parse_bank_csv_single_amount_column():
    csv_bytes = b"Date,Description,Amount\n01/15/2026,KROGER GROCERY,-45.20\n01/16/2026,PAYROLL,2000.00\n"
    result = parse_bank_csv(csv_bytes)
    assert len(result) == 2
    assert result[0] == {"date": "2026-01-15", "description": "KROGER GROCERY", "amount": -45.20}
    assert result[1]["amount"] == 2000.00


def test_parse_bank_csv_debit_credit_columns():
    csv_bytes = b"Posted Date,Memo,Debit,Credit\n02/01/2026,STARBUCKS,6.75,\n02/02/2026,PAYROLL,,2000.00\n"
    result = parse_bank_csv(csv_bytes)
    assert result[0]["amount"] == -6.75
    assert result[1]["amount"] == 2000.00


def test_parse_bank_csv_handles_parens_negative():
    csv_bytes = b"Date,Description,Amount\n03/01/2026,FEE,($5.00)\n"
    result = parse_bank_csv(csv_bytes)
    assert result[0]["amount"] == -5.00


def test_parse_bank_csv_missing_columns_raises():
    csv_bytes = b"Foo,Bar\n1,2\n"
    with pytest.raises(CsvImportError):
        parse_bank_csv(csv_bytes)


def test_parse_bank_csv_empty_raises():
    with pytest.raises(CsvImportError):
        parse_bank_csv(b"")


def test_parse_bank_csv_skips_unparseable_rows_but_keeps_valid_ones():
    csv_bytes = b"Date,Description,Amount\nnotadate,BAD ROW,10.00\n01/15/2026,GOOD ROW,-5.00\n"
    result = parse_bank_csv(csv_bytes)
    assert len(result) == 1
    assert result[0]["description"] == "GOOD ROW"
