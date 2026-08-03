import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from bank import crypto
from bank.config import get_bank_settings
from bank.errors import BankAuthError, BankConfigError, BankFetchError
from bank.psd2 import Psd2Client
from bank.scraper import ScraperClient
from bank.sync import store_transactions, sync_bank_transactions
from db import bill_applies_to_month, get_connection, get_salary_for_month, init_db, sync_recurring_bills
from mailer import MailerConfigError, MailerSendError, send_summary_email
from models import (
    BankConnectCreate,
    BankConnectionOut,
    BankConnectOtpSubmit,
    BankReverifyOtpSubmit,
    BankSyncOut,
    BankTransactionApprove,
    BankTransactionOut,
    BankTransactionsBulkApprove,
    CategoryCreate,
    CategoryOut,
    CategoryRuleCreate,
    CategoryRuleOut,
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
        "bank_txn_id": row["bank_txn_id"],
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
           c.color AS category_color, e.date, e.note, e.recurring_id, e.bank_txn_id
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_bank_connection(row) -> dict:
    return {
        "id": row["id"],
        "provider": row["provider"],
        "label": row["label"],
        "account_ref": row["account_ref"],
        "status": row["status"],
        "consent_valid_until": row["consent_valid_until"],
        "last_synced_at": row["last_synced_at"],
        "last_error": row["last_error"],
    }


BANK_TRANSACTION_JOIN_SELECT = """
    SELECT t.id, t.connection_id, t.external_id, t.booking_date, t.value_date, t.amount,
           t.currency, t.counterparty, t.description, t.status, t.suggested_category_id,
           t.expense_id, c.name AS suggested_category_name
    FROM bank_transactions t
    LEFT JOIN categories c ON c.id = t.suggested_category_id
"""


def row_to_bank_transaction(conn, row) -> dict:
    possible_duplicate = False
    if row["amount"] < 0:
        month = row["booking_date"][:7]
        bills = conn.execute("SELECT * FROM recurring_bills WHERE active = 1").fetchall()
        for bill in bills:
            if bill["amount"] == abs(row["amount"]) and bill_applies_to_month(bill, month):
                possible_duplicate = True
                break
    return {
        "id": row["id"],
        "connection_id": row["connection_id"],
        "external_id": row["external_id"],
        "booking_date": row["booking_date"],
        "value_date": row["value_date"],
        "amount": row["amount"],
        "currency": row["currency"],
        "counterparty": row["counterparty"],
        "description": row["description"],
        "status": row["status"],
        "suggested_category_id": row["suggested_category_id"],
        "suggested_category_name": row["suggested_category_name"],
        "expense_id": row["expense_id"],
        "possible_duplicate": possible_duplicate,
    }


def row_to_category_rule(row) -> dict:
    return {
        "id": row["id"],
        "pattern": row["pattern"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
    }


@app.get("/bank/connections", response_model=list[BankConnectionOut])
def list_bank_connections():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM bank_connections ORDER BY id").fetchall()
        return [row_to_bank_connection(r) for r in rows]
    finally:
        conn.close()


def _create_scraper_connection(conn, label: str, credentials: dict, scraped: dict) -> dict:
    if not scraped["accounts"]:
        raise HTTPException(status_code=502, detail="No accounts returned by scraper")

    account_ref = scraped["accounts"][0].account_ref
    secrets = crypto.encrypt(
        json.dumps({"credentials": credentials, "device_trust_data": scraped.get("device_trust_data")})
    )
    cur = conn.execute(
        """
        INSERT INTO bank_connections
            (provider, label, account_ref, status, secrets_enc, last_synced_at, created_at)
        VALUES ('scraper', ?, ?, 'valid', ?, ?, ?)
        """,
        (label, account_ref, secrets, _now(), _now()),
    )
    conn.commit()
    connection_id = cur.lastrowid

    txns = scraped["transactions_by_account"].get(account_ref, [])
    store_transactions(conn, connection_id, txns)

    row = conn.execute("SELECT * FROM bank_connections WHERE id = ?", (connection_id,)).fetchone()
    return row_to_bank_connection(row)


def _update_scraper_connection(conn, connection_id: int, scraped: dict) -> dict:
    """Refreshes an existing connection after re-verifying login (e.g. device
    trust expired and OTP was required again) — same shape as
    _create_scraper_connection but updates in place instead of inserting."""
    if not scraped["accounts"]:
        raise HTTPException(status_code=502, detail="No accounts returned by scraper")

    account_ref = scraped["accounts"][0].account_ref
    secrets = crypto.encrypt(
        json.dumps({"credentials": scraped["credentials"], "device_trust_data": scraped.get("device_trust_data")})
    )
    conn.execute(
        """
        UPDATE bank_connections
        SET account_ref = ?, status = 'valid', secrets_enc = ?, last_synced_at = ?, last_error = NULL
        WHERE id = ?
        """,
        (account_ref, secrets, _now(), connection_id),
    )
    conn.commit()

    txns = scraped["transactions_by_account"].get(account_ref, [])
    store_transactions(conn, connection_id, txns)

    row = conn.execute("SELECT * FROM bank_connections WHERE id = ?", (connection_id,)).fetchone()
    return row_to_bank_connection(row)


@app.post("/bank/connect", status_code=201)
def bank_connect(payload: BankConnectCreate):
    conn = get_connection()
    try:
        if payload.provider == "psd2":
            client = Psd2Client()
            try:
                consent = client.create_consent()
                oauth_meta = client.get_oauth_metadata(consent["sca_oauth_url"])
            except (BankAuthError, BankFetchError) as e:
                raise HTTPException(status_code=502, detail=str(e))

            secrets = crypto.encrypt(json.dumps({"oauth_metadata": oauth_meta}))
            cur = conn.execute(
                """
                INSERT INTO bank_connections
                    (provider, label, status, consent_id, secrets_enc, created_at)
                VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (payload.provider, payload.label, consent["consent_id"], secrets, _now()),
            )
            conn.commit()
            connection_id = cur.lastrowid

            settings = get_bank_settings()
            auth_url = client.build_authorization_url(
                oauth_meta, consent["consent_id"], settings.psd2_client_id, state=str(connection_id)
            )

            row = conn.execute(
                "SELECT * FROM bank_connections WHERE id = ?", (connection_id,)
            ).fetchone()
            result = row_to_bank_connection(row)
            result["sca_redirect_url"] = auth_url
            return result

        elif payload.provider == "scraper":
            if not payload.user_code or not payload.password:
                raise HTTPException(
                    status_code=422,
                    detail="user_code and password are required for the scraper provider",
                )
            credentials = {"userCode": payload.user_code, "password": payload.password}
            start_date = (date.today() - timedelta(days=30)).isoformat()
            try:
                result = ScraperClient().start_login(credentials, start_date)
            except BankAuthError as e:
                raise HTTPException(status_code=401, detail=str(e))

            if result["status"] == "otp_required":
                return {"status": "otp_required", "session_id": result["session_id"]}

            return _create_scraper_connection(conn, payload.label, credentials, result)

        else:
            raise HTTPException(status_code=422, detail="provider must be 'psd2' or 'scraper'")
    finally:
        conn.close()


@app.post("/bank/connect/otp")
def bank_connect_otp(payload: BankConnectOtpSubmit):
    conn = get_connection()
    try:
        try:
            result = ScraperClient().submit_otp(payload.session_id, payload.otp_code)
        except BankAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

        if result["status"] == "otp_required":
            return {"status": "otp_required", "session_id": result["session_id"]}

        return _create_scraper_connection(conn, payload.label, result["credentials"], result)
    finally:
        conn.close()


@app.get("/bank/callback", response_class=HTMLResponse)
def bank_callback(code: str, state: str):
    conn = get_connection()
    try:
        connection_id = int(state)
        connection = conn.execute(
            "SELECT * FROM bank_connections WHERE id = ?", (connection_id,)
        ).fetchone()
        if not connection:
            raise HTTPException(status_code=404, detail="Unknown bank connection")

        secrets = json.loads(crypto.decrypt(connection["secrets_enc"]))
        oauth_meta = secrets["oauth_metadata"]

        client = Psd2Client()
        settings = get_bank_settings()
        try:
            tokens = client.exchange_code(
                oauth_meta, code, settings.psd2_client_id, settings.psd2_client_secret
            )
            consent_status = client.get_consent_status(connection["consent_id"], tokens["access_token"])
            accounts = client.list_accounts(tokens["access_token"])
        except (BankAuthError, BankFetchError) as e:
            conn.execute(
                "UPDATE bank_connections SET status = 'error', last_error = ? WHERE id = ?",
                (str(e), connection_id),
            )
            conn.commit()
            raise HTTPException(status_code=502, detail=str(e))

        account_ref = accounts[0].account_ref if accounts else None
        new_secrets = crypto.encrypt(
            json.dumps({"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token")})
        )
        conn.execute(
            """
            UPDATE bank_connections
            SET status = ?, account_ref = ?, secrets_enc = ?, last_error = NULL
            WHERE id = ?
            """,
            (consent_status, account_ref, new_secrets, connection_id),
        )
        conn.commit()

        return "<html><body><h3>Bank account connected.</h3><p>You can close this tab and return to Expense Tracker.</p></body></html>"
    finally:
        conn.close()


@app.delete("/bank/connections/{connection_id}", status_code=204)
def delete_bank_connection(connection_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM bank_connections WHERE id = ?", (connection_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bank connection not found")

        if row["provider"] == "psd2" and row["consent_id"]:
            try:
                secrets = json.loads(crypto.decrypt(row["secrets_enc"])) if row["secrets_enc"] else {}
                access_token = secrets.get("access_token")
                if access_token:
                    Psd2Client().revoke_consent(row["consent_id"], access_token)
            except Exception:
                pass  # best-effort revoke; local deletion proceeds regardless

        # bank_transactions rows (and expenses.bank_txn_id referencing them) must
        # survive so already-imported expenses keep their provenance
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM bank_connections WHERE id = ?", (connection_id,))
        conn.commit()
        return None
    finally:
        conn.close()


@app.post("/bank/connections/{connection_id}/reverify")
def reverify_bank_connection(connection_id: int):
    """Re-runs login for a scraper connection using its stored credentials —
    used when device trust has expired and a sync starts asking for OTP again,
    so reconnecting doesn't require retyping the username/password."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bank_connections WHERE id = ?", (connection_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bank connection not found")
        if row["provider"] != "scraper":
            raise HTTPException(status_code=422, detail="Re-verification only applies to the scraper provider")

        secrets = json.loads(crypto.decrypt(row["secrets_enc"])) if row["secrets_enc"] else {}
        credentials = secrets.get("credentials")
        if not credentials:
            raise HTTPException(status_code=422, detail="No stored credentials for this connection")

        start_date = (date.today() - timedelta(days=30)).isoformat()
        try:
            result = ScraperClient().start_login(credentials, start_date)
        except BankAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

        if result["status"] == "otp_required":
            return {"status": "otp_required", "session_id": result["session_id"]}

        return _update_scraper_connection(conn, connection_id, result)
    finally:
        conn.close()


@app.post("/bank/connections/{connection_id}/reverify/otp")
def reverify_bank_connection_otp(connection_id: int, payload: BankReverifyOtpSubmit):
    conn = get_connection()
    try:
        try:
            result = ScraperClient().submit_otp(payload.session_id, payload.otp_code)
        except BankAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

        if result["status"] == "otp_required":
            return {"status": "otp_required", "session_id": result["session_id"]}

        return _update_scraper_connection(conn, connection_id, result)
    finally:
        conn.close()


@app.post("/bank/sync", response_model=BankSyncOut)
def bank_sync(connection_id: int, date_from: str, date_to: str):
    conn = get_connection()
    try:
        try:
            return sync_bank_transactions(conn, connection_id, date_from, date_to)
        except BankConfigError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except BankAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except BankFetchError as e:
            raise HTTPException(status_code=502, detail=str(e))
    finally:
        conn.close()


@app.get("/bank/transactions", response_model=list[BankTransactionOut])
def list_bank_transactions(status: str | None = None):
    conn = get_connection()
    try:
        query = BANK_TRANSACTION_JOIN_SELECT
        params = ()
        if status:
            query += " WHERE t.status = ?"
            params = (status,)
        query += " ORDER BY t.booking_date DESC, t.id DESC"
        rows = conn.execute(query, params).fetchall()
        return [row_to_bank_transaction(conn, r) for r in rows]
    finally:
        conn.close()


def _approve_transaction(conn, txn_row, category_id: int, note: str | None) -> int:
    category = conn.execute("SELECT id FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    expense_note = note if note is not None else txn_row["counterparty"] or txn_row["description"]
    cur = conn.execute(
        "INSERT INTO expenses (amount, category_id, date, note, bank_txn_id) VALUES (?, ?, ?, ?, ?)",
        (abs(txn_row["amount"]), category_id, txn_row["booking_date"], expense_note, txn_row["id"]),
    )
    conn.execute(
        "UPDATE bank_transactions SET status = 'approved', expense_id = ? WHERE id = ?",
        (cur.lastrowid, txn_row["id"]),
    )
    return cur.lastrowid


@app.post("/bank/transactions/{txn_id}/approve", response_model=BankTransactionOut)
def approve_bank_transaction(txn_id: int, payload: BankTransactionApprove):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bank transaction not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Transaction is already {row['status']}")

        _approve_transaction(conn, row, payload.category_id, payload.note)

        if payload.save_rule:
            pattern = payload.rule_pattern or row["counterparty"] or row["description"]
            if pattern:
                conn.execute(
                    "INSERT INTO category_rules (pattern, category_id, created_at) VALUES (?, ?, ?)",
                    (pattern, payload.category_id, _now()),
                )

        conn.commit()
        updated = conn.execute(
            BANK_TRANSACTION_JOIN_SELECT + " WHERE t.id = ?", (txn_id,)
        ).fetchone()
        return row_to_bank_transaction(conn, updated)
    finally:
        conn.close()


@app.post("/bank/transactions/{txn_id}/ignore", response_model=BankTransactionOut)
def ignore_bank_transaction(txn_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bank transaction not found")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail=f"Transaction is already {row['status']}")

        conn.execute("UPDATE bank_transactions SET status = 'ignored' WHERE id = ?", (txn_id,))
        conn.commit()
        updated = conn.execute(
            BANK_TRANSACTION_JOIN_SELECT + " WHERE t.id = ?", (txn_id,)
        ).fetchone()
        return row_to_bank_transaction(conn, updated)
    finally:
        conn.close()


@app.post("/bank/transactions/approve-bulk", response_model=list[BankTransactionOut])
def approve_bank_transactions_bulk(payload: BankTransactionsBulkApprove):
    conn = get_connection()
    try:
        updated_ids = []
        for txn_id in payload.ids:
            row = conn.execute("SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)).fetchone()
            if not row or row["status"] != "pending" or row["suggested_category_id"] is None:
                continue
            _approve_transaction(conn, row, row["suggested_category_id"], None)
            updated_ids.append(txn_id)
        conn.commit()

        rows = conn.execute(
            BANK_TRANSACTION_JOIN_SELECT + f" WHERE t.id IN ({','.join('?' * len(updated_ids))})",
            tuple(updated_ids),
        ).fetchall() if updated_ids else []
        return [row_to_bank_transaction(conn, r) for r in rows]
    finally:
        conn.close()


@app.get("/category-rules", response_model=list[CategoryRuleOut])
def list_category_rules():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.id, r.pattern, r.category_id, c.name AS category_name
            FROM category_rules r
            JOIN categories c ON c.id = r.category_id
            ORDER BY r.id
            """
        ).fetchall()
        return [row_to_category_rule(r) for r in rows]
    finally:
        conn.close()


@app.post("/category-rules", response_model=CategoryRuleOut, status_code=201)
def create_category_rule(payload: CategoryRuleCreate):
    conn = get_connection()
    try:
        category = conn.execute(
            "SELECT id FROM categories WHERE id = ?", (payload.category_id,)
        ).fetchone()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

        cur = conn.execute(
            "INSERT INTO category_rules (pattern, category_id, created_at) VALUES (?, ?, ?)",
            (payload.pattern, payload.category_id, _now()),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT r.id, r.pattern, r.category_id, c.name AS category_name
            FROM category_rules r JOIN categories c ON c.id = r.category_id
            WHERE r.id = ?
            """,
            (cur.lastrowid,),
        ).fetchone()
        return row_to_category_rule(row)
    finally:
        conn.close()


@app.delete("/category-rules/{rule_id}", status_code=204)
def delete_category_rule(rule_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM category_rules WHERE id = ?", (rule_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category rule not found")
        conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return None
    finally:
        conn.close()
