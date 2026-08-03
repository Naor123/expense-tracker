from bank.rules import suggest_category
from bank.types import NormalizedTxn


def test_falls_back_to_uncategorized_with_no_rules(conn):
    txn = NormalizedTxn(external_id="1", booking_date="2026-07-05", amount=-10, counterparty="Cofix", raw={})
    category_id = suggest_category(conn, txn)
    row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    assert row["name"] == "Uncategorized"


def test_matches_rule_by_counterparty_substring(conn):
    shopping = conn.execute("SELECT id FROM categories WHERE name = 'Shopping'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES (?, ?, ?)",
        ("super-pharm", shopping, "2026-01-01"),
    )
    conn.commit()

    txn = NormalizedTxn(external_id="1", booking_date="2026-07-05", amount=-10, counterparty="Super-Pharm Tel Aviv", raw={})
    assert suggest_category(conn, txn) == shopping


def test_matches_rule_is_case_insensitive_and_checks_description(conn):
    entertainment = conn.execute("SELECT id FROM categories WHERE name = 'Entertainment'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES (?, ?, ?)",
        ("NETFLIX", entertainment, "2026-01-01"),
    )
    conn.commit()

    txn = NormalizedTxn(
        external_id="1", booking_date="2026-07-05", amount=-10,
        counterparty=None, description="netflix.com subscription", raw={},
    )
    assert suggest_category(conn, txn) == entertainment


def test_first_matching_rule_wins(conn):
    bills = conn.execute("SELECT id FROM categories WHERE name = 'Bills'").fetchone()["id"]
    shopping = conn.execute("SELECT id FROM categories WHERE name = 'Shopping'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES (?, ?, ?)",
        ("Amazon", bills, "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES (?, ?, ?)",
        ("Amazon", shopping, "2026-01-02"),
    )
    conn.commit()

    txn = NormalizedTxn(external_id="1", booking_date="2026-07-05", amount=-10, counterparty="Amazon", raw={})
    assert suggest_category(conn, txn) == bills
