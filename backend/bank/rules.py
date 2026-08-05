from bank.seed_keywords import SEED_KEYWORDS
from bank.types import NormalizedTxn
from db import normalize_pattern


def _category_id_by_name(conn, name: str):
    row = conn.execute(
        "SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    return row["id"] if row else None


def suggest_category(conn, txn: NormalizedTxn):
    haystack = normalize_pattern(f"{txn.counterparty or ''} {txn.description or ''}")

    # Longest pattern first: a user who trained "סופר פארם" meant it to beat a
    # broader "סופר" every time, regardless of which they created first.
    rules = conn.execute(
        "SELECT pattern, category_id FROM category_rules ORDER BY LENGTH(pattern) DESC, id ASC"
    ).fetchall()
    for rule in rules:
        if rule["pattern"] and rule["pattern"] in haystack:
            return rule["category_id"]

    for pattern, category_name in SEED_KEYWORDS:
        if pattern in haystack:
            category_id = _category_id_by_name(conn, category_name)
            if category_id is not None:
                return category_id

    fallback = _category_id_by_name(conn, "Uncategorized")
    if fallback is not None:
        return fallback
    # "Uncategorized" is renameable and deletable from the UI, and losing it
    # must not take the whole sync down with it.
    row = conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None
