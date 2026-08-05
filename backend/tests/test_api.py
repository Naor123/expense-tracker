import pytest
from fastapi.testclient import TestClient

from bank.importer import materialize_expenses
from tests.test_importer import stage


@pytest.fixture
def client(conn):
    import main
    return TestClient(main.app)


def imported_expense(conn, bank_connection):
    txn_id = stage(conn, bank_connection, "tx-1", -50.0, counterparty="WOLT")
    materialize_expenses(conn, "2026-07")
    row = conn.execute("SELECT id FROM expenses WHERE bank_txn_id = ?", (txn_id,)).fetchone()
    return txn_id, row["id"]


def test_manual_expense_creation_is_gone(client):
    assert client.post("/expenses", json={"amount": 10, "category_id": 1, "date": "2026-07-15"}).status_code == 405


def test_patch_expense_updates_category_and_trains_a_rule(client, conn, bank_connection):
    _, expense_id = imported_expense(conn, bank_connection)
    car = conn.execute("SELECT id FROM categories WHERE name = 'Car'").fetchone()["id"]

    response = client.patch(f"/expenses/{expense_id}", json={"category_id": car, "remember": True})
    assert response.status_code == 200
    assert response.json()["category_id"] == car

    rule = conn.execute("SELECT pattern, category_id FROM category_rules").fetchone()
    assert rule["pattern"] == "wolt"
    assert rule["category_id"] == car


def test_repeated_corrections_leave_exactly_one_rule(client, conn, bank_connection):
    # The trap: a plain INSERT would leave the older rule in place and, because
    # matching returns the first hit, the second correction would never apply.
    _, expense_id = imported_expense(conn, bank_connection)
    car = conn.execute("SELECT id FROM categories WHERE name = 'Car'").fetchone()["id"]
    bills = conn.execute("SELECT id FROM categories WHERE name = 'Bills'").fetchone()["id"]

    client.patch(f"/expenses/{expense_id}", json={"category_id": car, "remember": True})
    client.patch(f"/expenses/{expense_id}", json={"category_id": bills, "remember": True})

    rules = conn.execute("SELECT pattern, category_id FROM category_rules").fetchall()
    assert len(rules) == 1
    assert rules[0]["category_id"] == bills


def test_patch_without_remember_trains_nothing(client, conn, bank_connection):
    _, expense_id = imported_expense(conn, bank_connection)
    car = conn.execute("SELECT id FROM categories WHERE name = 'Car'").fetchone()["id"]

    client.patch(f"/expenses/{expense_id}", json={"category_id": car, "remember": False})
    assert conn.execute("SELECT COUNT(*) AS c FROM category_rules").fetchone()["c"] == 0


def test_patch_on_a_rent_expense_trains_nothing(client, conn):
    cat = conn.execute("SELECT id FROM categories LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO expenses (amount, category_id, date, note, is_rent) VALUES (4500, ?, '2026-07-10', 'Rent', 1)",
        (cat,),
    )
    conn.commit()
    car = conn.execute("SELECT id FROM categories WHERE name = 'Car'").fetchone()["id"]

    assert client.patch(f"/expenses/{cur.lastrowid}", json={"category_id": car}).status_code == 200
    assert conn.execute("SELECT COUNT(*) AS c FROM category_rules").fetchone()["c"] == 0


def test_patch_with_unknown_category_is_404(client, conn, bank_connection):
    _, expense_id = imported_expense(conn, bank_connection)
    assert client.patch(f"/expenses/{expense_id}", json={"category_id": 9999}).status_code == 404


def test_deleting_an_imported_expense_ignores_the_transaction(client, conn, bank_connection):
    txn_id, expense_id = imported_expense(conn, bank_connection)

    assert client.delete(f"/expenses/{expense_id}").status_code == 204
    row = conn.execute(
        "SELECT status, ignore_reason, expense_id FROM bank_transactions WHERE id = ?", (txn_id,)
    ).fetchone()
    assert (row["status"], row["ignore_reason"], row["expense_id"]) == ("ignored", "user_deleted", None)


def test_restore_recreates_the_expense(client, conn, bank_connection):
    txn_id, expense_id = imported_expense(conn, bank_connection)
    client.delete(f"/expenses/{expense_id}")

    response = client.post(f"/bank/transactions/{txn_id}/restore")
    assert response.status_code == 200
    assert response.json()["status"] == "imported"
    assert conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"] == 1


def test_restore_on_a_non_ignored_transaction_is_409(client, conn, bank_connection):
    txn_id, _ = imported_expense(conn, bank_connection)
    assert client.post(f"/bank/transactions/{txn_id}/restore").status_code == 409


def test_backfill_materializes_staged_rows(client, conn, bank_connection):
    stage(conn, bank_connection, "tx-1", -50.0, counterparty="WOLT")

    response = client.post("/bank/backfill", params={"month": "2026-07"})
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"] == 1


def test_manual_salary_survives_a_later_materialize(client, conn, bank_connection):
    client.put("/salary", params={"month": "2026-07"}, json={"amount": 13000})
    stage(conn, bank_connection, "tx-salary", 17146.21)

    materialize_expenses(conn, "2026-07")
    assert client.get("/salary", params={"month": "2026-07"}).json()["amount"] == 13000


def test_clearing_a_manual_salary_lets_detection_take_over(client, conn, bank_connection):
    client.put("/salary", params={"month": "2026-07"}, json={"amount": 13000})
    stage(conn, bank_connection, "tx-salary", 17146.21)

    assert client.delete("/salary", params={"month": "2026-07"}).status_code == 204
    materialize_expenses(conn, "2026-07")

    body = client.get("/salary", params={"month": "2026-07"}).json()
    assert body["amount"] == 17146.21
    assert body["source"] == "auto"


def test_listing_transactions_by_month_uses_the_billing_window(client, conn, bank_connection):
    stage(conn, bank_connection, "tx-in", -10.0, booking_date="2026-07-15")
    stage(conn, bank_connection, "tx-out", -10.0, booking_date="2026-08-15")

    rows = client.get("/bank/transactions", params={"month": "2026-07"}).json()
    assert [r["external_id"] for r in rows] == ["tx-in"]
