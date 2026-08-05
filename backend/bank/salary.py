import os

from db import month_window, set_salary_for_month


def _salary_min() -> float:
    raw = os.getenv("SALARY_MIN")
    if not raw:
        return 3000.0
    try:
        return float(raw)
    except ValueError:
        return 3000.0


def recompute_salary_for_month(conn, month: str):
    """The largest incoming bank transfer in the month is the salary. Returns
    the winning bank_transactions.id, or None.

    Re-entrant on purpose: a bigger credit arriving mid-month demotes the
    previous winner, so running this after every sync converges rather than
    accumulating stale 'salary' rows. The SALARY_MIN floor stops a lone small
    refund from becoming "salary" and then propagating forward through
    get_salary_for_month's carry-forward lookup."""
    start, end = month_window(month)
    credits = conn.execute(
        """
        SELECT id, amount, kind FROM bank_transactions
        WHERE amount > 0 AND booking_date >= ? AND booking_date < ?
        ORDER BY amount DESC, id ASC
        """,
        (start, end),
    ).fetchall()

    winner = next(
        (r for r in credits if r["kind"] == "bank_transfer" and r["amount"] >= _salary_min()),
        None,
    )

    for row in credits:
        if winner and row["id"] == winner["id"]:
            continue
        reason = "incoming_credit" if row["kind"] == "bank_transfer" else "card_refund"
        conn.execute(
            "UPDATE bank_transactions SET status = 'ignored', ignore_reason = ? WHERE id = ?",
            (reason, row["id"]),
        )

    if not winner:
        return None

    conn.execute(
        "UPDATE bank_transactions SET status = 'salary', ignore_reason = NULL WHERE id = ?",
        (winner["id"],),
    )
    set_salary_for_month(conn, month, winner["amount"], source="auto")
    return winner["id"]
