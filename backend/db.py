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

SEED_RECURRING_BILLS = [
    ("Car Lease", 1450, "Car", 1, None, "2026-06"),
    ("Rent", 4500, "Bills", 1, None, "2026-06"),
    ("Arnona", 700, "Bills", 2, "odd", "2026-06"),
    ("Health Insurance", 130, "Bills", 1, None, "2026-06"),
    ("Internet (ISP)", 160, "Bills", 1, None, "2026-06"),
    ("AI Payment", 70, "Bills", 1, None, "2026-06"),
    ("Apple Music & iCloud", 40, "Entertainment", 1, None, "2026-06"),
    ("Gym", 150, "Entertainment", 1, None, "2026-06"),
]


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
            CREATE TABLE IF NOT EXISTS recurring_bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                category_id INTEGER NOT NULL REFERENCES categories(id),
                interval_months INTEGER NOT NULL DEFAULT 1,
                month_parity TEXT,
                start_month TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_generated (
                recurring_id INTEGER NOT NULL REFERENCES recurring_bills(id),
                month TEXT NOT NULL,
                expense_id INTEGER REFERENCES expenses(id),
                PRIMARY KEY (recurring_id, month)
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
        conn.commit()

        columns = [row["name"] for row in conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if "recurring_id" not in columns:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN recurring_id INTEGER REFERENCES recurring_bills(id)"
            )
            conn.commit()
        if "bank_txn_id" not in columns:
            conn.execute(
                "ALTER TABLE expenses ADD COLUMN bank_txn_id INTEGER REFERENCES bank_transactions(id)"
            )
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

        for bill_name, amount, category_name, interval_months, month_parity, start_month in SEED_RECURRING_BILLS:
            category = conn.execute(
                "SELECT id FROM categories WHERE name = ?", (category_name,)
            ).fetchone()
            if not category:
                continue
            conn.execute(
                """
                INSERT INTO recurring_bills
                    (name, amount, category_id, interval_months, month_parity, start_month, active)
                SELECT ?, ?, ?, ?, ?, ?, 1
                WHERE NOT EXISTS (SELECT 1 FROM recurring_bills WHERE name = ?)
                """,
                (bill_name, amount, category["id"], interval_months, month_parity, start_month, bill_name),
            )
        conn.commit()
    finally:
        conn.close()


def bill_applies_to_month(bill, month: str) -> bool:
    if month < bill["start_month"]:
        return False
    if bill["interval_months"] == 1:
        return True
    if bill["interval_months"] == 2:
        month_num = int(month[5:7])
        is_odd = month_num % 2 == 1
        if bill["month_parity"] == "odd":
            return is_odd
        if bill["month_parity"] == "even":
            return not is_odd
        return False
    return False


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


def sync_recurring_bills(conn):
    current_month = date.today().strftime("%Y-%m")
    bills = conn.execute(
        "SELECT * FROM recurring_bills WHERE active = 1"
    ).fetchall()

    for bill in bills:
        if current_month < bill["start_month"]:
            continue
        for month in months_between(bill["start_month"], current_month):
            if not bill_applies_to_month(bill, month):
                continue
            already = conn.execute(
                "SELECT 1 FROM recurring_generated WHERE recurring_id = ? AND month = ?",
                (bill["id"], month),
            ).fetchone()
            if already:
                continue
            cur = conn.execute(
                "INSERT INTO expenses (amount, category_id, date, note, recurring_id) VALUES (?, ?, ?, ?, ?)",
                (bill["amount"], bill["category_id"], f"{month}-01", bill["name"], bill["id"]),
            )
            conn.execute(
                "INSERT INTO recurring_generated (recurring_id, month, expense_id) VALUES (?, ?, ?)",
                (bill["id"], month, cur.lastrowid),
            )
    conn.commit()
