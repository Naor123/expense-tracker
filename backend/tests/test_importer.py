from bank.importer import materialize_expenses
from bank.sync import store_transactions
from bank.types import NormalizedTxn
from db import RENT_AMOUNT


def stage(conn, connection_id, external_id, amount, booking_date="2026-07-15",
          value_date=None, kind="bank_transfer", settlement="immediate",
          counterparty="Test Merchant", status="new"):
    cur = conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, created_at)
        VALUES (?, ?, ?, ?, ?, 'ILS', ?, '', '{}', ?, ?, ?, '2026-01-01T00:00:00+00:00')
        """,
        (connection_id, external_id, booking_date, value_date, amount, counterparty,
         status, kind, settlement),
    )
    conn.commit()
    return cur.lastrowid


def expense_count(conn):
    return conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]


def status_of(conn, txn_id):
    row = conn.execute(
        "SELECT status, ignore_reason FROM bank_transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    return row["status"], row["ignore_reason"]


def test_debit_becomes_an_expense(conn, bank_connection):
    txn_id = stage(conn, bank_connection, "tx-1", -50.0)
    result = materialize_expenses(conn, "2026-07")

    assert result["imported"] == 1
    row = conn.execute("SELECT * FROM expenses WHERE bank_txn_id = ?", (txn_id,)).fetchone()
    assert row["amount"] == 50.0  # sign stripped
    assert row["date"] == "2026-07-15"
    assert row["note"] == "Test Merchant"
    assert status_of(conn, txn_id)[0] == "imported"


def test_materialize_is_idempotent(conn, bank_connection):
    stage(conn, bank_connection, "tx-1", -50.0)
    materialize_expenses(conn, "2026-07")
    second = materialize_expenses(conn, "2026-07")

    assert second["imported"] == 0
    assert expense_count(conn) == 1


def test_rows_outside_the_month_are_left_staged(conn, bank_connection):
    # 2026-07 window is [2026-07-10, 2026-08-10)
    outside = stage(conn, bank_connection, "tx-out", -50.0, booking_date="2026-08-20")
    materialize_expenses(conn, "2026-07")

    assert expense_count(conn) == 0
    assert status_of(conn, outside)[0] == "new"


def test_user_deleted_rows_are_never_reimported(conn, bank_connection):
    txn_id = stage(conn, bank_connection, "tx-1", -50.0)
    materialize_expenses(conn, "2026-07")

    expense = conn.execute("SELECT id FROM expenses WHERE bank_txn_id = ?", (txn_id,)).fetchone()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense["id"],))
    conn.execute(
        "UPDATE bank_transactions SET status = 'ignored', expense_id = NULL, ignore_reason = 'user_deleted' WHERE id = ?",
        (txn_id,),
    )
    conn.commit()

    materialize_expenses(conn, "2026-07")
    assert expense_count(conn) == 0
    assert status_of(conn, txn_id) == ("ignored", "user_deleted")


def test_rent_amount_is_ignored_when_rent_was_generated(conn, bank_connection):
    cat = conn.execute("SELECT id FROM categories LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO expenses (amount, category_id, date, note, is_rent) VALUES (?, ?, '2026-07-10', 'Rent', 1)",
        (RENT_AMOUNT, cat),
    )
    conn.execute(
        "INSERT INTO rent_generated (month, expense_id) VALUES ('2026-07', ?)", (cur.lastrowid,)
    )
    conn.commit()
    txn_id = stage(conn, bank_connection, "tx-rent", -float(RENT_AMOUNT), counterparty="הוראת-קבע")
    materialize_expenses(conn, "2026-07")

    assert status_of(conn, txn_id) == ("ignored", "rent_duplicate")
    assert expense_count(conn) == 1  # only the generated rent row


def test_rent_amount_is_imported_when_no_rent_was_generated(conn, bank_connection):
    txn_id = stage(conn, bank_connection, "tx-rent", -float(RENT_AMOUNT))
    materialize_expenses(conn, "2026-07")

    assert status_of(conn, txn_id)[0] == "imported"
    assert expense_count(conn) == 1


def test_bulk_card_payment_ignored_even_when_staged_before_its_itemized_rows(conn, bank_connection):
    # Insert order is deliberately "wrong" — the lump sum first. The whole point
    # of a deferred pass is that ordering no longer decides whether money doubles.
    bulk = stage(
        conn, bank_connection, "tx-bulk", -1200.0, booking_date="2026-07-11",
        value_date="2026-08-10", kind="credit_card_payment", settlement="delayed",
        counterparty="MAX",
    )
    stage(
        conn, bank_connection, "card-1", -27.0, booking_date="2026-07-20",
        value_date="2026-08-10", kind="credit_card_charge", settlement="delayed",
        counterparty="HATACO",
    )
    materialize_expenses(conn, "2026-07")

    assert status_of(conn, bulk) == ("ignored", "card_lump_sum")


def test_bulk_card_payment_imported_when_no_itemized_data_exists(conn, bank_connection):
    bulk = stage(
        conn, bank_connection, "tx-bulk", -1200.0, booking_date="2026-07-11",
        value_date="2026-08-10", kind="credit_card_payment", settlement="delayed",
        counterparty="MAX",
    )
    materialize_expenses(conn, "2026-07")

    assert status_of(conn, bulk)[0] == "imported"


def test_itemized_duplicate_keeps_the_card_row_and_ignores_the_bank_twin(conn, bank_connection):
    # The real shape from live data: the bank feed shows "מסטרקרד ₪46.37" and the
    # card itemization shows "AMAZON PRIME ₪46.37" two days apart. Same money.
    bank_row = stage(
        conn, bank_connection, "tx-bank", -46.37, booking_date="2026-07-11",
        kind="bank_transfer", settlement="immediate", counterparty="מסטרקרד",
    )
    card_row = stage(
        conn, bank_connection, "tx-card", -46.37, booking_date="2026-07-10",
        value_date="2026-07-12", kind="credit_card_charge", settlement="immediate",
        counterparty="AMAZON PRIME",
    )
    materialize_expenses(conn, "2026-07")

    assert status_of(conn, bank_row) == ("ignored", "itemized_duplicate")
    assert status_of(conn, card_row)[0] == "imported"
    assert expense_count(conn) == 1

    expense = conn.execute("SELECT note FROM expenses").fetchone()
    assert expense["note"] == "AMAZON PRIME"  # the informative name survives


def test_itemized_duplicate_ignores_delayed_card_charges(conn, bank_connection):
    # A same-priced domestic purchase riding the delayed cycle is a genuinely
    # different transaction, not a twin — only fast-settling charges appear twice.
    bank_row = stage(
        conn, bank_connection, "tx-bank", -11.90, booking_date="2026-07-27",
        kind="bank_transfer", settlement="immediate",
    )
    stage(
        conn, bank_connection, "tx-card", -11.90, booking_date="2026-07-25",
        value_date="2026-08-10", kind="credit_card_charge", settlement="delayed",
    )
    materialize_expenses(conn, "2026-07")

    assert status_of(conn, bank_row)[0] == "imported"
    assert expense_count(conn) == 2


def test_category_is_assigned_from_rules_over_seed_keywords(conn, bank_connection):
    cat = conn.execute("SELECT id FROM categories WHERE name = 'Car'").fetchone()["id"]
    conn.execute(
        "INSERT INTO category_rules (pattern, category_id, created_at) VALUES ('wolt', ?, '2026-01-01')",
        (cat,),
    )
    conn.commit()
    stage(conn, bank_connection, "tx-1", -50.0, counterparty="WOLT")
    materialize_expenses(conn, "2026-07")

    row = conn.execute("SELECT category_id FROM expenses").fetchone()
    assert row["category_id"] == cat


def test_category_falls_back_to_seed_keywords(conn, bank_connection):
    stage(conn, bank_connection, "tx-1", -50.0, counterparty="WOLT")
    materialize_expenses(conn, "2026-07")

    row = conn.execute(
        "SELECT c.name FROM expenses e JOIN categories c ON c.id = e.category_id"
    ).fetchone()
    assert row["name"] == "Going Out"


def test_unknown_merchant_is_uncategorized(conn, bank_connection):
    stage(conn, bank_connection, "tx-1", -50.0, counterparty="העברה בBIT")
    materialize_expenses(conn, "2026-07")

    row = conn.execute(
        "SELECT c.name FROM expenses e JOIN categories c ON c.id = e.category_id"
    ).fetchone()
    assert row["name"] == "Uncategorized"


def test_month_end_normalized_merchant_dates_to_last_calendar_day(conn, bank_connection):
    # The car lease settles near month-end but the exact day drifts with
    # weekends/bank holidays -- pin it to a stable date instead of trusting
    # whichever day the bank happened to report.
    txn_id = stage(conn, bank_connection, "tx-lease", -2786.70, booking_date="2026-07-10", counterparty='שלמה פסגה בע"מ')
    materialize_expenses(conn, "2026-07")

    row = conn.execute("SELECT date FROM expenses WHERE bank_txn_id = ?", (txn_id,)).fetchone()
    assert row["date"] == "2026-07-31"


def test_full_sync_path_stages_then_materializes(conn, bank_connection):
    txn = NormalizedTxn(
        external_id="tx-1", booking_date="2026-07-15", amount=-64.0,
        currency="ILS", counterparty="WOLT", raw={},
    )
    store_transactions(conn, bank_connection, [txn])
    assert expense_count(conn) == 0

    materialize_expenses(conn, "2026-07")
    assert expense_count(conn) == 1
