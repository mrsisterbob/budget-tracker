"""Budget Tracker: import a bank statement CSV, auto-categorize into necessary/discretionary/
income buckets, and serve chart-ready summaries (income over time, spending breakdown wheel).

Deliberately a single small Flask app with server-rendered chart data (no separate frontend
build step) - this is meant to run privately (behind the auth layer the future unifying site
will add) as a personal utility, not a public-facing product.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from flask import Flask, jsonify, render_template, request

import database
from categorizer import categorize_transaction, load_rules
from csv_importer import CsvImportError, parse_bank_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = Flask(__name__)
database.init_db()


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/import", methods=["POST"])
def import_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded (expected multipart field 'file')."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename."}), 400

    try:
        raw_transactions = parse_bank_csv(file.read())
    except CsvImportError as e:
        return jsonify({"error": str(e)}), 400

    rules = load_rules()
    categorized = []
    for t in raw_transactions:
        result = categorize_transaction(t["description"], t["amount"], rules)
        categorized.append({**t, **result})

    result = database.insert_transactions(categorized)
    return jsonify({
        "message": f"Imported {result['inserted']} transactions ({result['skipped_duplicates']} duplicates skipped).",
        **result,
    }), 200


@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    start = request.args.get("start")
    end = request.args.get("end")
    return jsonify(database.get_all_transactions(start_date=start, end_date=end))


@app.route("/api/transactions/<int:transaction_id>", methods=["DELETE"])
def remove_transaction(transaction_id):
    deleted = database.delete_transaction(transaction_id)
    return jsonify({"deleted": deleted}), (200 if deleted else 404)


@app.route("/api/transactions/<int:transaction_id>/category", methods=["PATCH"])
def recategorize_transaction(transaction_id):
    payload = request.get_json(silent=True) or {}
    bucket = payload.get("bucket")
    category = payload.get("category")
    if bucket not in ("necessary", "discretionary", "income", "uncategorized"):
        return jsonify({"error": "bucket must be one of: necessary, discretionary, income, uncategorized"}), 400
    if not category:
        return jsonify({"error": "category is required"}), 400
    updated = database.update_transaction_category(transaction_id, bucket, category)
    return jsonify({"updated": updated}), (200 if updated else 404)


@app.route("/api/summary/income-over-time", methods=["GET"])
def income_over_time():
    """Monthly net income (income bucket total - all expense buckets total), for a line/bar
    chart of income trend over time."""
    transactions = database.get_all_transactions()
    monthly = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    for t in transactions:
        month_key = t["date"][:7]  # YYYY-MM
        if t["bucket"] == "income":
            monthly[month_key]["income"] += t["amount"]
        else:
            monthly[month_key]["expenses"] += abs(t["amount"])

    months = sorted(monthly.keys())
    return jsonify({
        "months": months,
        "income": [round(monthly[m]["income"], 2) for m in months],
        "expenses": [round(monthly[m]["expenses"], 2) for m in months],
        "net": [round(monthly[m]["income"] - monthly[m]["expenses"], 2) for m in months],
    })


@app.route("/api/summary/spending-wheel", methods=["GET"])
def spending_wheel():
    """Discretionary vs. necessary breakdown, plus per-category totals within each - the data
    for the donut/wheel chart. Only counts expenses (negative amounts), income is excluded."""
    start = request.args.get("start")
    end = request.args.get("end")
    transactions = database.get_all_transactions(start_date=start, end_date=end)

    bucket_totals = defaultdict(float)
    category_totals = defaultdict(lambda: defaultdict(float))
    for t in transactions:
        if t["bucket"] == "income":
            continue
        amount = abs(t["amount"])
        bucket_totals[t["bucket"]] += amount
        category_totals[t["bucket"]][t["category"]] += amount

    return jsonify({
        "bucket_totals": {k: round(v, 2) for k, v in bucket_totals.items()},
        "categories": {
            bucket: {cat: round(total, 2) for cat, total in cats.items()}
            for bucket, cats in category_totals.items()
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
