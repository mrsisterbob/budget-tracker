# budget-tracker

A personal budget tracker: import a bank statement CSV, auto-categorize each transaction into
necessary/discretionary/income buckets via editable keyword rules, and view income-over-time and
spending-breakdown charts.

## Architecture

```
main.py                    Flask app: import endpoint, chart-data endpoints, serves the UI.
csv_importer.py             Flexible bank-CSV parser - auto-detects Date/Description/Amount or
                             Debit/Credit column pairs across common export formats.
categorizer.py               Keyword-based bucket/category assignment, rules loaded from JSON.
categorization_rules.json    Editable ruleset (necessary/discretionary/income keyword lists).
                              Edit and re-import - no code change needed to retune categories.
database.py                  SQLite persistence with content-based dedup (re-importing an
                              overlapping statement never double-counts a transaction).
templates/index.html         Single-page UI: CSV upload + two Chart.js charts.
test_budget_tracker.py       Unit tests for the parser and categorizer (no network/DB required).
```

## Setup

```
pip install -r requirements.txt
python main.py
```

Visit `http://localhost:5002`, upload a CSV export from your bank, and the charts populate
automatically. Tune `categorization_rules.json` to match your own spending patterns - it's
reloaded fresh on every import.

## Notes on the CSV parser

Built generic on purpose since it wasn't built against a real Huntington Bank export directly -
it recognizes common header names (`Date`/`Posted Date`, `Description`/`Memo`/`Payee`,
`Amount`, or a `Debit`/`Credit` pair). If your real export uses different column headers than it
recognizes, add them to the alias lists at the top of `csv_importer.py`.

## Tests

```
python -m pytest test_budget_tracker.py -v
```
