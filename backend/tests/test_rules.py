from bank.rules import suggest_category
from bank.types import NormalizedTxn


def test_falls_back_to_uncategorized_when_nothing_matches(conn):
    txn = NormalizedTxn(
        external_id="1", booking_date="2026-07-05", amount=-10,
        counterparty="Zzz Unknown Merchant", raw={},
    )
    category_id = suggest_category(conn, txn)
    row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    assert row["name"] == "Uncategorized"


def test_seed_keywords_apply_when_no_rule_matches(conn):
    txn = NormalizedTxn(external_id="1", booking_date="2026-07-05", amount=-10, counterparty="Cofix", raw={})
    category_id = suggest_category(conn, txn)
    row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
    assert row["name"] == "Going Out"


def test_a_learned_rule_beats_a_seed_keyword(conn):
    bills = conn.execute("SELECT id FROM categories WHERE name = 'Bills'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES ('netflix', ?, '2026-01-01')",
        (bills,),
    )
    conn.commit()

    txn = NormalizedTxn(external_id="1", booking_date="2026-07-05", amount=-10, counterparty="NETFLIX", raw={})
    assert suggest_category(conn, txn) == bills


def test_matches_across_collapsed_whitespace(conn):
    # Live counterparties arrive with runs of spaces; a correct pattern must
    # still match through them.
    food = conn.execute("SELECT id FROM categories WHERE name = 'food'").fetchone()
    if food is None:
        food = conn.execute("SELECT id FROM categories WHERE name = 'Bills'").fetchone()
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES ('סופר אל הים', ?, '2026-01-01')",
        (food["id"],),
    )
    conn.commit()

    txn = NormalizedTxn(
        external_id="1", booking_date="2026-07-05", amount=-10, counterparty="סופר  אל הים", raw={}
    )
    assert suggest_category(conn, txn) == food["id"]


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


def test_longest_matching_rule_wins(conn):
    # A user who trained the more specific pattern meant it to win, regardless
    # of which rule they happened to create first.
    bills = conn.execute("SELECT id FROM categories WHERE name = 'Bills'").fetchone()["id"]
    shopping = conn.execute("SELECT id FROM categories WHERE name = 'Shopping'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES ('amazon', ?, '2026-01-01')",
        (bills,),
    )
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES ('amazon prime', ?, '2026-01-02')",
        (shopping,),
    )
    conn.commit()

    txn = NormalizedTxn(
        external_id="1", booking_date="2026-07-05", amount=-10, counterparty="AMAZON PRIME", raw={}
    )
    assert suggest_category(conn, txn) == shopping
