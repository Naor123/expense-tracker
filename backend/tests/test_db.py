import db


def test_deleted_builtin_recurring_bill_is_not_reseeded_on_restart(conn):
    rent = conn.execute("SELECT id FROM recurring_bills WHERE name = 'Rent'").fetchone()
    assert rent is not None

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM recurring_bills WHERE id = ?", (rent["id"],))
    conn.commit()

    db.init_db()  # simulates the app restarting

    rows = conn.execute("SELECT * FROM recurring_bills WHERE name = 'Rent'").fetchall()
    assert rows == []
