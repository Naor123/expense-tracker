import db


def test_bucket_month_before_the_10th_shifts_back_a_month():
    assert db.bucket_month("2026-08-01") == "2026-07"
    assert db.bucket_month("2026-08-09") == "2026-07"


def test_bucket_month_on_or_after_the_10th_stays_in_month():
    assert db.bucket_month("2026-08-10") == "2026-08"
    assert db.bucket_month("2026-08-31") == "2026-08"


def test_bucket_month_handles_year_rollover():
    assert db.bucket_month("2027-01-05") == "2026-12"


def test_month_window_matches_bucket_month_at_its_boundaries():
    start, end = db.month_window("2026-08")
    assert (start, end) == ("2026-08-10", "2026-09-10")
    assert db.bucket_month(start) == "2026-08"
    assert db.bucket_month(end) == "2026-09"  # end is exclusive
    assert db.bucket_month("2026-09-09") == "2026-08"  # just inside the window


def test_sync_rent_generates_one_expense_per_month_since_start(conn):
    db.sync_rent(conn)

    rows = conn.execute("SELECT date, amount, note, is_rent FROM expenses WHERE is_rent = 1 ORDER BY date").fetchall()
    months = db.months_between(db.RENT_START_MONTH, db.current_bucket_month())
    assert len(rows) == len(months)
    for row in rows:
        assert row["amount"] == db.RENT_AMOUNT
        assert row["note"] == "Rent"
        assert bool(row["is_rent"]) is True


def test_sync_rent_is_idempotent(conn):
    db.sync_rent(conn)
    count_after_first = conn.execute("SELECT COUNT(*) AS c FROM expenses WHERE is_rent = 1").fetchone()["c"]

    db.sync_rent(conn)
    count_after_second = conn.execute("SELECT COUNT(*) AS c FROM expenses WHERE is_rent = 1").fetchone()["c"]

    assert count_after_first == count_after_second


def test_deleting_a_generated_rent_expense_is_not_recreated(conn):
    db.sync_rent(conn)
    row = conn.execute("SELECT id FROM expenses WHERE is_rent = 1 ORDER BY date LIMIT 1").fetchone()

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM expenses WHERE id = ?", (row["id"],))
    conn.commit()

    db.sync_rent(conn)

    still_gone = conn.execute("SELECT id FROM expenses WHERE id = ?", (row["id"],)).fetchone()
    assert still_gone is None


def _insert_rent_txn(conn, booking_date):
    conn.execute(
        """
        INSERT INTO bank_connections (provider, label, status, created_at)
        VALUES ('scraper', 'Test Bank', 'valid', '2026-01-01')
        """
    )
    conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, created_at)
        VALUES (1, 'rent-1', ?, ?, ?, 'ILS', 'הוראת-קבע', '', '{}', 'new', 'bank_transfer', 'immediate', '2026-01-01T00:00:00+00:00')
        """,
        (booking_date, booking_date, -float(db.RENT_AMOUNT)),
    )
    conn.commit()


def test_sync_rent_uses_the_real_transaction_date_when_already_synced(conn):
    _insert_rent_txn(conn, "2026-07-31")
    db.sync_rent(conn)

    row = conn.execute(
        "SELECT e.date FROM expenses e JOIN rent_generated rg ON rg.expense_id = e.id WHERE rg.month = '2026-07'"
    ).fetchone()
    assert row["date"] == "2026-07-31"


def test_sync_rent_backfills_the_real_date_once_it_arrives_later(conn):
    db.sync_rent(conn)  # first run: no real transaction yet, placeholder date
    placeholder = conn.execute(
        "SELECT e.date FROM expenses e JOIN rent_generated rg ON rg.expense_id = e.id WHERE rg.month = '2026-07'"
    ).fetchone()
    assert placeholder["date"] == "2026-07-10"

    _insert_rent_txn(conn, "2026-07-31")
    db.sync_rent(conn)  # second run: real transaction now visible

    updated = conn.execute(
        "SELECT e.date FROM expenses e JOIN rent_generated rg ON rg.expense_id = e.id WHERE rg.month = '2026-07'"
    ).fetchone()
    assert updated["date"] == "2026-07-31"


def test_last_calendar_day_of_month():
    assert db.last_calendar_day_of_month("2026-07") == "2026-07-31"
    assert db.last_calendar_day_of_month("2026-02") == "2026-02-28"
    assert db.last_calendar_day_of_month("2026-12") == "2026-12-31"
