from typing import Optional

from bank.classify import CREDIT_CARD_COMPANY_IDS
from bank.rules import suggest_category
from bank.salary import recompute_salary_for_month
from bank.types import NormalizedTxn
from db import (
    RENT_AMOUNT,
    bucket_month,
    last_calendar_day_of_month,
    month_window,
    normalize_pattern,
    previous_month,
)

# Merchants that post around the 10th of the month but whose charge is for
# the period ending BEFORE that cutoff — the payment belongs to the prior
# month's spending even though it lands in the current bucket by the usual
# day>=10 rule. The exact posting day also drifts a little with weekends/bank
# holidays, so rather than trust it literally, pin the date to the last
# calendar day of the month the charge actually belongs to.
MONTH_END_NORMALIZED_MERCHANTS = [
    "שלמה פסגה",  # car lease
]


def _normalize_expense_date(counterparty: Optional[str], booking_date: str) -> str:
    haystack = normalize_pattern(counterparty or "")
    if any(pattern in haystack for pattern in MONTH_END_NORMALIZED_MERCHANTS):
        return last_calendar_day_of_month(previous_month(booking_date[:7]))
    return booking_date


def _has_active_credit_card_connection(conn, exclude_connection_id: int) -> bool:
    placeholders = ",".join("?" * len(CREDIT_CARD_COMPANY_IDS))
    row = conn.execute(
        f"""
        SELECT 1 FROM bank_connections
        WHERE status = 'valid' AND id != ? AND company_id IN ({placeholders})
        LIMIT 1
        """,
        (exclude_connection_id, *CREDIT_CARD_COMPANY_IDS),
    ).fetchone()
    return row is not None


def _has_itemized_charge_for_debit_date(conn, connection_id: int, value_date: Optional[str]) -> bool:
    if not value_date:
        return False
    row = conn.execute(
        "SELECT 1 FROM bank_transactions WHERE connection_id = ? AND kind = 'credit_card_charge' AND value_date = ? LIMIT 1",
        (connection_id, value_date),
    ).fetchone()
    return row is not None


def has_itemized_twin(conn, row) -> bool:
    """True if this bank-feed row is the same purchase as an itemized card
    charge sitting elsewhere in the table.

    Deliberately does NOT constrain connection_id: Hapoalim's own card
    itemization lives on the same connection as its bank feed, so a
    cross-connection-only check misses that pair entirely. The settlement
    filter is what keeps this honest — only fast-settling foreign-currency
    charges appear on both feeds, so two same-priced domestic purchases in the
    same week don't collide."""
    if row["kind"] != "bank_transfer":
        return False
    anchor = row["booking_date"]
    if not anchor:
        return False
    match = conn.execute(
        """
        SELECT 1 FROM bank_transactions
        WHERE id != ? AND kind = 'credit_card_charge' AND settlement = 'immediate'
          AND amount = ? AND value_date IS NOT NULL
          AND ABS(julianday(value_date) - julianday(?)) <= 3
        LIMIT 1
        """,
        (row["id"], row["amount"], anchor),
    ).fetchone()
    return match is not None


def _has_generated_rent(conn, booking_date: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM rent_generated WHERE month = ?", (bucket_month(booking_date),)
    ).fetchone()
    return row is not None


def _ignore_reason_for(conn, row) -> Optional[str]:
    if row["kind"] == "credit_card_payment" and (
        _has_active_credit_card_connection(conn, row["connection_id"])
        or _has_itemized_charge_for_debit_date(conn, row["connection_id"], row["value_date"])
    ):
        return "card_lump_sum"
    if abs(row["amount"]) == RENT_AMOUNT and _has_generated_rent(conn, row["booking_date"]):
        return "rent_duplicate"
    # Tie-break is by kind, not by which row we happen to visit first: the
    # itemized card charge carries the real merchant name ("AMAZON PRIME"),
    # the bank-feed twin only carries the card network ("מסטרקרד"). Ignoring
    # whichever row is flagged would drop both and lose the expense.
    if has_itemized_twin(conn, row):
        return "itemized_duplicate"
    return None


def create_expense_from_transaction(conn, row, category_id: int) -> int:
    note = row["counterparty"] or row["description"]
    expense_date = _normalize_expense_date(row["counterparty"], row["booking_date"])
    cur = conn.execute(
        "INSERT INTO expenses (amount, category_id, date, note, bank_txn_id) VALUES (?, ?, ?, ?, ?)",
        (abs(row["amount"]), category_id, expense_date, note, row["id"]),
    )
    conn.execute(
        "UPDATE bank_transactions SET status = 'imported', expense_id = ?, ignore_reason = NULL WHERE id = ?",
        (cur.lastrowid, row["id"]),
    )
    return cur.lastrowid


def _already_materialized(conn, row) -> bool:
    if row["expense_id"] is None:
        return False
    return (
        conn.execute("SELECT 1 FROM expenses WHERE id = ?", (row["expense_id"],)).fetchone()
        is not None
    )


def materialize_expenses(conn, month: str) -> dict:
    """Turns staged bank_transactions into expenses for one billing month.

    Runs as a pass over already-stored rows rather than inline during sync, so
    it stays idempotent (re-running imports nothing new), retryable, and free
    of the insert-ordering constraints the ignore checks would otherwise
    impose on the sync itself."""
    start, end = month_window(month)
    salary_id = recompute_salary_for_month(conn, month)

    rows = conn.execute(
        """
        SELECT * FROM bank_transactions
        WHERE booking_date >= ? AND booking_date < ? AND status = 'new'
        ORDER BY id
        """,
        (start, end),
    ).fetchall()

    imported = 0
    ignored = 0
    for row in rows:
        if _already_materialized(conn, row) or row["amount"] >= 0:
            continue
        reason = _ignore_reason_for(conn, row)
        if reason:
            conn.execute(
                "UPDATE bank_transactions SET status = 'ignored', ignore_reason = ? WHERE id = ?",
                (reason, row["id"]),
            )
            ignored += 1
            continue
        category_id = suggest_category(
            conn,
            NormalizedTxn(
                external_id=row["external_id"],
                booking_date=row["booking_date"],
                value_date=row["value_date"],
                amount=row["amount"],
                currency=row["currency"],
                counterparty=row["counterparty"],
                description=row["description"],
                raw={},
            ),
        )
        if category_id is None:
            conn.execute(
                "UPDATE bank_transactions SET status = 'ignored', ignore_reason = 'no_category' WHERE id = ?",
                (row["id"],),
            )
            ignored += 1
            continue
        conn.execute(
            "UPDATE bank_transactions SET suggested_category_id = ? WHERE id = ?",
            (category_id, row["id"]),
        )
        create_expense_from_transaction(conn, row, category_id)
        imported += 1

    conn.commit()
    return {"imported": imported, "ignored": ignored, "salary": 1 if salary_id else 0}
