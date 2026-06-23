import os
import re
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db import get_connection, get_salary_for_month, init_db, sync_recurring_bills
from mailer import MailerConfigError, MailerSendError, send_summary_email
from models import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ExpenseCreate,
    ExpenseOut,
    InsightsEmailOut,
    RecurringBillCreate,
    RecurringBillOut,
    RecurringBillUpdate,
    SalaryOut,
    SalaryUpdate,
    SummaryOut,
)

app = FastAPI(title="Expense Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@app.on_event("startup")
def on_startup():
    init_db()
    conn = get_connection()
    try:
        sync_recurring_bills(conn)
    finally:
        conn.close()


def validate_month(month: str | None) -> str:
    if not month or not MONTH_RE.match(month):
        raise HTTPException(status_code=422, detail="month must be in YYYY-MM format")
    return month


def row_to_category(row) -> dict:
    return {"id": row["id"], "name": row["name"], "color": row["color"]}


def row_to_expense(row) -> dict:
    return {
        "id": row["id"],
        "amount": row["amount"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "category_color": row["category_color"],
        "date": row["date"],
        "note": row["note"],
        "recurring_id": row["recurring_id"],
    }


def row_to_recurring_bill(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "amount": row["amount"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "category_color": row["category_color"],
        "interval_months": row["interval_months"],
        "month_parity": row["month_parity"],
        "start_month": row["start_month"],
        "active": bool(row["active"]),
    }


EXPENSE_JOIN_SELECT = """
    SELECT e.id, e.amount, e.category_id, c.name AS category_name,
           c.color AS category_color, e.date, e.note, e.recurring_id
    FROM expenses e
    JOIN categories c ON c.id = e.category_id
"""

RECURRING_BILL_JOIN_SELECT = """
    SELECT r.id, r.name, r.amount, r.category_id, c.name AS category_name,
           c.color AS category_color, r.interval_months, r.month_parity,
           r.start_month, r.active
    FROM recurring_bills r
    JOIN categories c ON c.id = r.category_id
"""


@app.get("/categories", response_model=list[CategoryOut])
def list_categories():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, color FROM categories ORDER BY id").fetchall()
        return [row_to_category(r) for r in rows]
    finally:
        conn.close()


@app.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (payload.name,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Category name already exists")
        cur = conn.execute(
            "INSERT INTO categories (name, color) VALUES (?, ?)",
            (payload.name, payload.color),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, color FROM categories WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return row_to_category(row)
    finally:
        conn.close()


@app.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, payload: CategoryUpdate):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, color FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")

        new_name = payload.name if payload.name is not None else row["name"]
        new_color = payload.color if payload.color is not None else row["color"]

        if payload.name is not None:
            conflict = conn.execute(
                "SELECT id FROM categories WHERE LOWER(name) = LOWER(?) AND id != ?",
                (payload.name, category_id),
            ).fetchone()
            if conflict:
                raise HTTPException(status_code=409, detail="Category name already exists")

        conn.execute(
            "UPDATE categories SET name = ?, color = ? WHERE id = ?",
            (new_name, new_color, category_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT id, name, color FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        return row_to_category(updated)
    finally:
        conn.close()


@app.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")

        total_categories = conn.execute("SELECT COUNT(*) AS c FROM categories").fetchone()["c"]
        if total_categories <= 1:
            raise HTTPException(status_code=409, detail="Cannot delete the last remaining category")

        expense_count = conn.execute(
            "SELECT COUNT(*) AS c FROM expenses WHERE category_id = ?", (category_id,)
        ).fetchone()["c"]
        if expense_count > 0:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete category: expenses reference this category",
            )

        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
        return None
    finally:
        conn.close()


@app.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(month: str | None = None):
    validate_month(month)
    conn = get_connection()
    try:
        sync_recurring_bills(conn)
        rows = conn.execute(
            EXPENSE_JOIN_SELECT
            + " WHERE e.date LIKE ? ORDER BY e.date DESC, e.id DESC",
            (f"{month}-%",),
        ).fetchall()
        return [row_to_expense(r) for r in rows]
    finally:
        conn.close()


@app.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseCreate):
    conn = get_connection()
    try:
        category = conn.execute(
            "SELECT id FROM categories WHERE id = ?", (payload.category_id,)
        ).fetchone()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        cur = conn.execute(
            "INSERT INTO expenses (amount, category_id, date, note) VALUES (?, ?, ?, ?)",
            (payload.amount, payload.category_id, payload.date, payload.note),
        )
        conn.commit()
        row = conn.execute(
            EXPENSE_JOIN_SELECT + " WHERE e.id = ?", (cur.lastrowid,)
        ).fetchone()
        return row_to_expense(row)
    finally:
        conn.close()


@app.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Expense not found")
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
        return None
    finally:
        conn.close()


def compute_summary(conn, month: str) -> dict:
    rows = conn.execute(
        """
        SELECT c.id AS category_id, c.name AS name, c.color AS color,
               SUM(e.amount) AS amount
        FROM expenses e
        JOIN categories c ON c.id = e.category_id
        WHERE e.date LIKE ?
        GROUP BY c.id, c.name, c.color
        HAVING SUM(e.amount) > 0
        ORDER BY amount DESC
        """,
        (f"{month}-%",),
    ).fetchall()

    total = sum(r["amount"] for r in rows)
    categories = []
    for r in rows:
        percent = round((r["amount"] / total * 100), 1) if total else 0
        categories.append(
            {
                "category_id": r["category_id"],
                "name": r["name"],
                "color": r["color"],
                "amount": round(r["amount"], 2),
                "percent": percent,
            }
        )

    return {"month": month, "total": round(total, 2), "categories": categories}


@app.get("/summary", response_model=SummaryOut)
def get_summary(month: str | None = None):
    validate_month(month)
    conn = get_connection()
    try:
        sync_recurring_bills(conn)
        return compute_summary(conn, month)
    finally:
        conn.close()


@app.post("/insights/send-email", response_model=InsightsEmailOut)
def send_insights_email(month: str | None = None):
    validate_month(month)
    conn = get_connection()
    try:
        sync_recurring_bills(conn)
        summary = compute_summary(conn, month)
        salary = get_salary_for_month(conn, month)
    finally:
        conn.close()

    if salary is None:
        raise HTTPException(
            status_code=503,
            detail="Net salary is not set. Set it in the Net Salary section before sending insights.",
        )

    try:
        send_summary_email(month, summary, salary)
    except MailerConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except MailerSendError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"sent": True, "recipient": os.getenv("RECIPIENT_EMAIL", "")}


@app.get("/salary", response_model=SalaryOut)
def get_salary(month: str | None = None):
    validate_month(month)
    conn = get_connection()
    try:
        amount = get_salary_for_month(conn, month)
        return {"month": month, "amount": amount}
    finally:
        conn.close()


@app.put("/salary", response_model=SalaryOut)
def set_salary(payload: SalaryUpdate, month: str | None = None):
    validate_month(month)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO monthly_salary (month, amount) VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET amount = excluded.amount
            """,
            (month, payload.amount),
        )
        conn.commit()
        return {"month": month, "amount": payload.amount}
    finally:
        conn.close()


@app.get("/months", response_model=list[str])
def list_months():
    conn = get_connection()
    try:
        sync_recurring_bills(conn)
        rows = conn.execute(
            """
            SELECT DISTINCT substr(date, 1, 7) AS month
            FROM expenses
            ORDER BY month DESC
            """
        ).fetchall()
        months = [r["month"] for r in rows]
        if not months:
            return [date.today().strftime("%Y-%m")]
        return months
    finally:
        conn.close()


@app.get("/recurring-bills", response_model=list[RecurringBillOut])
def list_recurring_bills():
    conn = get_connection()
    try:
        rows = conn.execute(RECURRING_BILL_JOIN_SELECT + " ORDER BY r.id").fetchall()
        return [row_to_recurring_bill(r) for r in rows]
    finally:
        conn.close()


@app.post("/recurring-bills", response_model=RecurringBillOut, status_code=201)
def create_recurring_bill(payload: RecurringBillCreate):
    conn = get_connection()
    try:
        category = conn.execute(
            "SELECT id FROM categories WHERE id = ?", (payload.category_id,)
        ).fetchone()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        if payload.interval_months == 2 and payload.month_parity not in ("odd", "even"):
            raise HTTPException(
                status_code=422,
                detail="month_parity must be 'odd' or 'even' when interval_months is 2",
            )

        start_month = payload.start_month or date.today().strftime("%Y-%m")
        validate_month(start_month)

        cur = conn.execute(
            """
            INSERT INTO recurring_bills
                (name, amount, category_id, interval_months, month_parity, start_month, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                payload.name,
                payload.amount,
                payload.category_id,
                payload.interval_months,
                payload.month_parity,
                start_month,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid

        sync_recurring_bills(conn)

        row = conn.execute(
            RECURRING_BILL_JOIN_SELECT + " WHERE r.id = ?", (new_id,)
        ).fetchone()
        return row_to_recurring_bill(row)
    finally:
        conn.close()


@app.put("/recurring-bills/{bill_id}", response_model=RecurringBillOut)
def update_recurring_bill(bill_id: int, payload: RecurringBillUpdate):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM recurring_bills WHERE id = ?", (bill_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recurring bill not found")

        if payload.category_id is not None:
            category = conn.execute(
                "SELECT id FROM categories WHERE id = ?", (payload.category_id,)
            ).fetchone()
            if not category:
                raise HTTPException(status_code=404, detail="Category not found")

        if payload.apply_amount_to is not None and payload.apply_amount_to not in ("current", "all"):
            raise HTTPException(status_code=422, detail="apply_amount_to must be 'current' or 'all'")

        new_name = payload.name if payload.name is not None else row["name"]
        new_amount = payload.amount if payload.amount is not None else row["amount"]
        new_category_id = (
            payload.category_id if payload.category_id is not None else row["category_id"]
        )
        new_active = payload.active if payload.active is not None else bool(row["active"])

        conn.execute(
            "UPDATE recurring_bills SET name = ?, amount = ?, category_id = ?, active = ? WHERE id = ?",
            (new_name, new_amount, new_category_id, int(new_active), bill_id),
        )

        if payload.amount is not None and payload.amount != row["amount"]:
            apply_scope = payload.apply_amount_to or "current"
            if apply_scope == "all":
                conn.execute(
                    "UPDATE expenses SET amount = ? WHERE recurring_id = ?",
                    (new_amount, bill_id),
                )
            else:
                current_month = date.today().strftime("%Y-%m")
                conn.execute(
                    "UPDATE expenses SET amount = ? WHERE recurring_id = ? AND date LIKE ?",
                    (new_amount, bill_id, f"{current_month}-%"),
                )

        conn.commit()

        updated = conn.execute(
            RECURRING_BILL_JOIN_SELECT + " WHERE r.id = ?", (bill_id,)
        ).fetchone()
        return row_to_recurring_bill(updated)
    finally:
        conn.close()


@app.delete("/recurring-bills/{bill_id}", status_code=204)
def delete_recurring_bill(bill_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM recurring_bills WHERE id = ?", (bill_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recurring bill not found")
        # generated expenses/recurring_generated rows reference this id and must
        # survive the delete, so FK enforcement is relaxed for this statement only
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM recurring_bills WHERE id = ?", (bill_id,))
        conn.commit()
        return None
    finally:
        conn.close()
