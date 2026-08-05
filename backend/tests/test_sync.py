from bank.scraper import _map_card_itemized_transaction
from bank.sync import store_card_itemized_transactions, store_transactions
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
    assert all(r["status"] == "new" for r in rows)


def test_store_transactions_is_idempotent(conn, bank_connection):
    txns = [make_txn("tx-1"), make_txn("tx-2")]
    store_transactions(conn, bank_connection, txns)
    result = store_transactions(conn, bank_connection, txns)
    assert result == {"fetched": 2, "inserted": 0, "skipped": 2}

    count = conn.execute("SELECT COUNT(*) AS c FROM bank_transactions").fetchone()["c"]
    assert count == 2


def test_staging_does_not_decide_status(conn, bank_connection):
    # Credits, debits and card lump sums all stage identically — every routing
    # decision belongs to materialize_expenses, which sees the whole table.
    store_transactions(conn, bank_connection, [
        make_txn("tx-credit", amount=12000.0),
        make_txn("tx-debit", amount=-30.0),
    ])
    rows = conn.execute("SELECT status FROM bank_transactions").fetchall()
    assert {r["status"] for r in rows} == {"new"}


def test_staging_does_not_create_expenses(conn, bank_connection):
    store_transactions(conn, bank_connection, [make_txn("tx-1")])
    assert conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"] == 0


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


def test_credit_card_company_transactions_are_tagged(conn, bank_connection):
    store_transactions(conn, bank_connection, [make_txn("tx-purchase")], "max")
    row = conn.execute("SELECT kind FROM bank_transactions WHERE external_id = 'tx-purchase'").fetchone()
    assert row["kind"] == "credit_card_charge"


def test_force_kind_overrides_classification(conn, bank_connection):
    store_transactions(conn, bank_connection, [make_txn("tx-1")], force_kind="credit_card_charge")
    row = conn.execute("SELECT kind FROM bank_transactions WHERE external_id = 'tx-1'").fetchone()
    assert row["kind"] == "credit_card_charge"


def test_force_settlement_overrides_date_based_classification(conn, bank_connection):
    # Same calendar month booking/value would classify as 'immediate' by date
    # comparison alone — force_settlement must win regardless.
    txn = make_txn("tx-forced", amount=-10.0)
    txn = txn.model_copy(update={"booking_date": "2026-08-01", "value_date": "2026-08-10"})
    store_transactions(conn, bank_connection, [txn], force_settlement="delayed")
    row = conn.execute("SELECT settlement FROM bank_transactions WHERE external_id = 'tx-forced'").fetchone()
    assert row["settlement"] == "delayed"


def test_target_month_discards_transactions_outside_the_window(conn, bank_connection):
    # 2026-08 bucket window is [2026-08-10, 2026-09-10); an Aug-1 txn (day < 10)
    # buckets into July and must be dropped when target_month='2026-08'.
    in_window = make_txn("tx-in-window").model_copy(update={"booking_date": "2026-08-15"})
    out_of_window = make_txn("tx-out-of-window").model_copy(update={"booking_date": "2026-08-01"})
    result = store_transactions(conn, bank_connection, [in_window, out_of_window], target_month="2026-08")
    assert result == {"fetched": 2, "inserted": 1, "skipped": 1}

    rows = conn.execute("SELECT external_id FROM bank_transactions").fetchall()
    assert [r["external_id"] for r in rows] == ["tx-in-window"]


def test_store_card_itemized_transactions_splits_by_origin(conn, bank_connection):
    national = NormalizedTxn(
        external_id="card-national", booking_date="2026-08-01", value_date="2026-08-10",
        amount=-27.0, counterparty="HATACO", raw={"origin": 1},
    )
    international = NormalizedTxn(
        external_id="card-international", booking_date="2026-08-01", value_date="2026-08-03",
        amount=-11.9, counterparty="APPLE", raw={"origin": 2},
    )
    result = store_card_itemized_transactions(conn, bank_connection, [national, international], "hapoalim")
    assert result == {"fetched": 2, "inserted": 2, "skipped": 0}

    nat_row = conn.execute("SELECT kind, settlement FROM bank_transactions WHERE external_id = 'card-national'").fetchone()
    assert (nat_row["kind"], nat_row["settlement"]) == ("credit_card_charge", "delayed")

    intl_row = conn.execute(
        "SELECT kind, settlement FROM bank_transactions WHERE external_id = 'card-international'"
    ).fetchone()
    assert (intl_row["kind"], intl_row["settlement"]) == ("credit_card_charge", "immediate")


def test_map_card_itemized_transaction():
    txn = _map_card_itemized_transaction({
        "externalId": "card-1484-6001139-20260810",
        "merchantName": "HATACO",
        "amount": 27.0,
        "eventDate": "20260801",
        "debitDate": "20260810",
    })
    assert txn.booking_date == "2026-08-01"
    assert txn.value_date == "2026-08-10"
    assert txn.amount == -27.0
    assert txn.counterparty == "HATACO"
