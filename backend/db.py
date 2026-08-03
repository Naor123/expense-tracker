import os
import sqlite3
from datetime import date

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "expenses.db")

SEED_CATEGORIES = [
    ("Bills", "#FF6B6B"),
    ("Shopping", "#4D96FF"),
    ("Car", "#FFD93D"),
    ("Entertainment", "#6BCB77"),
    ("Going Out", "#FF8C42"),
    ("Uncategorized", "#9CA3AF"),
]

# Everything except Rent comes from the bank/card sync now. Rent is the one
# fixed, known amount not otherwise represented cleanly in the imported feed
# (it shows up on the bank side as a same-day standing order, hence 'immediate'),
# so it stays a hardcoded monthly generator instead of a user-editable table.
RENT_AMOUNT = 4500
RENT_CATEGORY_NAME = "Bills"
RENT_START_MONTH = "2026-06"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                date TEXT NOT NULL,
                note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rent_generated (
                month TEXT PRIMARY KEY,
                expense_id INTEGER REFERENCES expenses(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_salary (
                month TEXT PRIMARY KEY,
                amount REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                label TEXT NOT NULL,
                account_ref TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                consent_id TEXT,
                consent_valid_until TEXT,
                secrets_enc TEXT,
                last_synced_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bank_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL REFERENCES bank_connections(id),
                external_id TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                value_date TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'ILS',
                counterparty TEXT,
                description TEXT,
                raw_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                suggested_category_id INTEGER REFERENCES categories(id),
                expense_id INTEGER REFERENCES expenses(id),
                created_at TEXT NOT NULL,
                UNIQUE (connection_id, external_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS salary_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

        # One-time cleanup — the old user-editable recurring bills feature is
        # gone; Rent is now the only recurring item, tracked via `is_rent`
        # below and `rent_generated` instead of a bill-id foreign key.
        # `expenses.recurring_id` must be dropped before `recurring_bills`
        # itself — it's the other FK pointing at that table (besides
        # recurring_generated, dropped first here), and DROP TABLE fails
        # under foreign_keys=ON while any non-null column still references it.
        conn.execute("DROP TABLE IF EXISTS recurring_generated")
        conn.commit()

        columns = [row["name"] for row in conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if "recurring_id" in columns:
            conn.execute("ALTER TABLE expenses DROP COLUMN recurring_id")
            conn.commit()
            columns = [row["name"] for row in conn.execute("PRAGMA table_info(expenses)").fetchall()]

        conn.execute("DROP TABLE IF EXISTS recurring_bills")
        conn.commit()

        if "is_rent" not in columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN is_rent INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "bank_txn_id" not in columns:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN bank_txn_id INTEGER REFERENCES bank_transactions(id)"
            )
            conn.commit()

        connection_columns = [row["name"] for row in conn.execute("PRAGMA table_info(bank_connections)").fetchall()]
        if "company_id" not in connection_columns:
            conn.execute("ALTER TABLE bank_connections ADD COLUMN company_id TEXT")
            conn.commit()

        txn_columns = [row["name"] for row in conn.execute("PRAGMA table_info(bank_transactions)").fetchall()]
        if "kind" not in txn_columns:
            conn.execute("ALTER TABLE bank_transactions ADD COLUMN kind TEXT NOT NULL DEFAULT 'bank_transfer'")
            conn.commit()
        if "settlement" not in txn_columns:
            conn.execute("ALTER TABLE bank_transactions ADD COLUMN settlement TEXT NOT NULL DEFAULT 'immediate'")
            conn.commit()

        for name, color in SEED_CATEGORIES:
            conn.execute(
                """
                INSERT INTO categories (name, color)
                SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = ?)
                """,
                (name, color, name),
            )
        conn.commit()
    finally:
        conn.close()


def months_between(start_month: str, end_month: str):
    start_year, start_mon = int(start_month[:4]), int(start_month[5:7])
    end_year, end_mon = int(end_month[:4]), int(end_month[5:7])
    months = []
    y, m = start_year, start_mon
    while (y, m) <= (end_year, end_mon):
        months.append(f"{y:04d}-{m:02d}")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return months


def get_salary_for_month(conn, month: str):
    row = conn.execute(
        "SELECT amount FROM monthly_salary WHERE month <= ? ORDER BY month DESC LIMIT 1",
        (month,),
    ).fetchone()
    if row:
        return row["amount"]
    env_default = os.getenv("MONTHLY_SALARY")
    if env_default:
        try:
            return float(env_default)
        except ValueError:
            return None
    return None


def set_salary_for_month(conn, month: str, amount: float):
    conn.execute(
        """
        INSERT INTO monthly_salary (month, amount) VALUES (?, ?)
        ON CONFLICT(month) DO UPDATE SET amount = excluded.amount
        """,
        (month, amount),
    )


def sync_rent(conn):
    category = conn.execute(
        "SELECT id FROM categories WHERE name = ?", (RENT_CATEGORY_NAME,)
    ).fetchone()
    if not category:
        return

    current_month = date.today().strftime("%Y-%m")
    for month in months_between(RENT_START_MONTH, current_month):
        already = conn.execute("SELECT 1 FROM rent_generated WHERE month = ?", (month,)).fetchone()
        if already:
            continue
        cur = conn.execute(
            "INSERT INTO expenses (amount, category_id, date, note, is_rent) VALUES (?, ?, ?, 'Rent', 1)",
            (RENT_AMOUNT, category["id"], f"{month}-01"),
        )
        conn.execute(
            "INSERT INTO rent_generated (month, expense_id) VALUES (?, ?)",
            (month, cur.lastrowid),
        )
    conn.commit()
