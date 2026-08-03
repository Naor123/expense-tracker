from bank.types import NormalizedTxn


def suggest_category(conn, txn: NormalizedTxn) -> int:
    haystack = f"{txn.counterparty or ''} {txn.description or ''}".lower()
    rules = conn.execute(
        "SELECT pattern, category_id FROM category_rules ORDER BY id"
    ).fetchall()
    for rule in rules:
        if rule["pattern"].lower() in haystack:
            return rule["category_id"]

    fallback = conn.execute(
        "SELECT id FROM categories WHERE name = 'Uncategorized'"
    ).fetchone()
    return fallback["id"]
