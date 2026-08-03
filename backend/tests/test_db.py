from datetime import date

import db


def test_sync_rent_generates_one_expense_per_month_since_start(conn):
    db.sync_rent(conn)

    rows = conn.execute("SELECT date, amount, note, is_rent FROM expenses WHERE is_rent = 1 ORDER BY date").fetchall()
    months = db.months_between(db.RENT_START_MONTH, date.today().strftime("%Y-%m"))
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
