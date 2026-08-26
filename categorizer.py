"""Keyword-based transaction categorization: rules live in categorization_rules.json, not code,
so tuning which merchants count as "necessary" vs "discretionary" never requires a redeploy -
same hot-reload-JSON-bank pattern used across the other repos in this project family.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

RULES_PATH = Path(__file__).parent / "categorization_rules.json"

# bucket name -> whether it counts as income (not an expense at all)
INCOME_BUCKET = "income"


def load_rules() -> dict:
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logging.error(f"Failed to load categorization rules, using empty ruleset: {e}")
        return {"necessary": {}, "discretionary": {}, "income": {}, "uncategorized_bucket": "Uncategorized"}


def categorize_transaction(description: str, amount: float, rules: dict | None = None) -> dict:
    """Returns {"bucket": "necessary"|"discretionary"|"income"|"uncategorized", "category": str}.

    A positive amount is treated as income only if it also matches an income keyword rule -
    a positive amount alone isn't proof of income (e.g. a refund into a normally-expense
    category should still land in that category, not be miscounted as a paycheck).
    """
    rules = rules or load_rules()
    desc_lower = (description or "").lower()

    for bucket in ("income", "necessary", "discretionary"):
        for category, keywords in rules.get(bucket, {}).items():
            if any(kw.lower() in desc_lower for kw in keywords):
                return {"bucket": bucket, "category": category}

    # Fallback: unmatched positive amounts are assumed income, unmatched negative are uncategorized
    # expenses - a reasonable default that keeps the income chart useful even before rules are tuned.
    if amount > 0:
        return {"bucket": "income", "category": "Other Income (unmatched)"}
    return {"bucket": "uncategorized", "category": rules.get("uncategorized_bucket", "Uncategorized")}
