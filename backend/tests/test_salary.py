from bank.salary import recompute_salary_for_month
from db import get_salary_for_month, set_salary_for_month
from tests.test_importer import stage, status_of


def salary_row(conn, month):
    return conn.execute(
        "SELECT amount, source FROM monthly_salary WHERE month = ?", (month,)
    ).fetchone()


def test_largest_bank_credit_becomes_salary(conn, bank_connection):
    small = stage(conn, bank_connection, "tx-small", 5000.0)
    big = stage(conn, bank_connection, "tx-big", 17146.21)
    recompute_salary_for_month(conn, "2026-07")

    assert status_of(conn, big)[0] == "salary"
    assert status_of(conn, small) == ("ignored", "incoming_credit")
    assert salary_row(conn, "2026-07")["amount"] == 17146.21


def test_card_side_credit_is_ignored_as_a_refund(conn, bank_connection):
    refund = stage(conn, bank_connection, "tx-refund", 50.0, kind="credit_card_charge")
    recompute_salary_for_month(conn, "2026-07")

    assert status_of(conn, refund) == ("ignored", "card_refund")


def test_credit_below_the_floor_is_not_salary(conn, bank_connection):
    # Otherwise a lone refund becomes "salary" and carries forward into every
    # later month via get_salary_for_month's month <= ? lookup.
    small = stage(conn, bank_connection, "tx-small", 50.0)
    recompute_salary_for_month(conn, "2026-07")

    assert status_of(conn, small) == ("ignored", "incoming_credit")
    assert salary_row(conn, "2026-07") is None


def test_a_larger_credit_demotes_the_previous_winner(conn, bank_connection):
    first = stage(conn, bank_connection, "tx-first", 9000.0)
    recompute_salary_for_month(conn, "2026-07")
    assert status_of(conn, first)[0] == "salary"

    second = stage(conn, bank_connection, "tx-second", 17000.0)
    recompute_salary_for_month(conn, "2026-07")

    assert status_of(conn, second)[0] == "salary"
    assert status_of(conn, first) == ("ignored", "incoming_credit")
    assert salary_row(conn, "2026-07")["amount"] == 17000.0


def test_manual_salary_is_never_overwritten_by_detection(conn, bank_connection):
    set_salary_for_month(conn, "2026-07", 13000.0, source="manual")
    conn.commit()
    stage(conn, bank_connection, "tx-big", 17146.21)
    recompute_salary_for_month(conn, "2026-07")

    row = salary_row(conn, "2026-07")
    assert row["amount"] == 13000.0
    assert row["source"] == "manual"


def test_auto_salary_is_overwritten_by_detection(conn, bank_connection):
    set_salary_for_month(conn, "2026-07", 100.0, source="auto")
    conn.commit()
    stage(conn, bank_connection, "tx-big", 17146.21)
    recompute_salary_for_month(conn, "2026-07")

    assert salary_row(conn, "2026-07")["amount"] == 17146.21


def test_credit_before_the_10th_keys_the_previous_bucket_month(conn, bank_connection):
    # Aug 3 falls inside July's billing window [2026-07-10, 2026-08-10).
    stage(conn, bank_connection, "tx-salary", 17146.21, booking_date="2026-08-03")
    recompute_salary_for_month(conn, "2026-07")

    assert salary_row(conn, "2026-07")["amount"] == 17146.21
    assert salary_row(conn, "2026-08") is None


def test_salary_carries_forward_to_later_months(conn, bank_connection):
    stage(conn, bank_connection, "tx-salary", 17146.21)
    recompute_salary_for_month(conn, "2026-07")

    assert get_salary_for_month(conn, "2026-09") == 17146.21
