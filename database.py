"""SQLite persistence for imported transactions. Same WAL-mode connection pattern as the
crypto_engine and docfiler repos, for consistency across the project family."""
from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "budget_tracker.db")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_hash TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    bucket TEXT NOT NULL,
    category TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_bucket ON transactions(bucket);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_db_conn() as conn:
        conn.executescript(_SCHEMA_SQL)


def compute_dedup_hash(date: str, description: str, amount: float) -> str:
    """Re-importing the same statement (or an overlapping date range from a fresh export)
    should never double-count a transaction - hash on the fields that uniquely identify one."""
    raw = f"{date}|{description.strip().lower()}|{amount:.2f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def insert_transactions(transactions: list[dict]) -> dict:
    """Bulk-inserts, skipping any that already exist (by dedup_hash). Returns
    {"inserted": n, "skipped_duplicates": n} so an import can report what actually happened."""
    inserted = 0
    skipped = 0
    now = utcnow_iso()
    with get_db_conn() as conn:
        for t in transactions:
            dedup_hash = compute_dedup_hash(t["date"], t["description"], t["amount"])
            try:
                conn.execute(
                    """INSERT INTO transactions (dedup_hash, date, description, amount, bucket, category, imported_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (dedup_hash, t["date"], t["description"], t["amount"], t["bucket"], t["category"], now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return {"inserted": inserted, "skipped_duplicates": skipped}


def get_all_transactions(start_date: str = None, end_date: str = None) -> list[dict]:
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date ASC"
    with get_db_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_transaction(transaction_id: int) -> bool:
    with get_db_conn() as conn:
        cursor = conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        return cursor.rowcount > 0


def update_transaction_category(transaction_id: int, bucket: str, category: str) -> bool:
    """Manual override for a single transaction - the keyword ruleset won't always get it
    right, and re-importing shouldn't force you to keep re-correcting the same one."""
    with get_db_conn() as conn:
        cursor = conn.execute(
            "UPDATE transactions SET bucket = ?, category = ? WHERE id = ?",
            (bucket, category, transaction_id),
        )
        return cursor.rowcount > 0
