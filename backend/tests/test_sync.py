from bank.sync import store_transactions
from bank.types import NormalizedTxn


def make_txn(external_id, amount=-50.0):
    return NormalizedTxn(
        external_id=external_id,
        booking_date="2026-07-05",
        amount=amount,
        currency="ILS",
        counterparty="Test Merchant",
        description="Card purchase",
        raw={"transactionId": external_id},
    )


def test_store_transactions_inserts_new_rows(conn, bank_connection):
    result = store_transactions(conn, bank_connection, [make_txn("tx-1"), make_txn("tx-2")])
    assert result == {"fetched": 2, "inserted": 2, "skipped": 0}

    rows = conn.execute("SELECT external_id, status FROM bank_transactions ORDER BY external_id").fetchall()
    assert [r["external_id"] for r in rows] == ["tx-1", "tx-2"]
    assert all(r["status"] == "pending" for r in rows)


def test_store_transactions_is_idempotent(conn, bank_connection):
    txns = [make_txn("tx-1"), make_txn("tx-2")]
    store_transactions(conn, bank_connection, txns)
    result = store_transactions(conn, bank_connection, txns)
    assert result == {"fetched": 2, "inserted": 0, "skipped": 2}

    count = conn.execute("SELECT COUNT(*) AS c FROM bank_transactions").fetchone()["c"]
    assert count == 2


def test_credits_are_auto_ignored(conn, bank_connection):
    result = store_transactions(conn, bank_connection, [make_txn("tx-salary", amount=12000.0)])
    assert result["inserted"] == 1

    row = conn.execute("SELECT status FROM bank_transactions WHERE external_id = 'tx-salary'").fetchone()
    assert row["status"] == "ignored"


def test_debits_are_pending(conn, bank_connection):
    store_transactions(conn, bank_connection, [make_txn("tx-debit", amount=-30.0)])
    row = conn.execute("SELECT status FROM bank_transactions WHERE external_id = 'tx-debit'").fetchone()
    assert row["status"] == "pending"


def test_different_connections_can_share_external_id(conn, bank_connection):
    cur = conn.execute(
        """
        INSERT INTO bank_connections (provider, label, status, created_at)
        VALUES ('scraper', 'Other Bank', 'valid', '2026-01-01')
        """
    )
    conn.commit()
    other_connection = cur.lastrowid

    store_transactions(conn, bank_connection, [make_txn("tx-shared")])
    result = store_transactions(conn, other_connection, [make_txn("tx-shared")])
    assert result["inserted"] == 1  # unique index is scoped per-connection


def make_card_payment_txn(external_id):
    return NormalizedTxn(
        external_id=external_id,
        booking_date="2026-07-05",
        amount=-1200.0,
        currency="ILS",
        counterparty="MAX",
        description="monthly card charge",
        raw={"transactionId": external_id},
    )


def test_bank_side_card_payment_stays_pending_without_a_card_connection(conn, bank_connection):
    store_transactions(conn, bank_connection, [make_card_payment_txn("tx-card")], "hapoalim")
    row = conn.execute("SELECT status, kind FROM bank_transactions WHERE external_id = 'tx-card'").fetchone()
    assert row["kind"] == "credit_card_payment"
    assert row["status"] == "pending"


def test_bank_side_card_payment_is_ignored_when_a_card_connection_is_active(conn, bank_connection):
    conn.execute(
        """
        INSERT INTO bank_connections (provider, company_id, label, status, created_at)
        VALUES ('scraper', 'max', 'My Max Card', 'valid', '2026-01-01')
        """
    )
    conn.commit()

    store_transactions(conn, bank_connection, [make_card_payment_txn("tx-card")], "hapoalim")
    row = conn.execute("SELECT status, kind FROM bank_transactions WHERE external_id = 'tx-card'").fetchone()
    assert row["kind"] == "credit_card_payment"
    assert row["status"] == "ignored"


def test_credit_card_company_transactions_are_tagged_and_stay_pending(conn, bank_connection):
    store_transactions(conn, bank_connection, [make_txn("tx-purchase")], "max")
    row = conn.execute("SELECT status, kind FROM bank_transactions WHERE external_id = 'tx-purchase'").fetchone()
    assert row["kind"] == "credit_card_charge"
    assert row["status"] == "pending"
