import os
import re
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
        if "ignore_reason" not in txn_columns:
            conn.execute("ALTER TABLE bank_transactions ADD COLUMN ignore_reason TEXT")
            conn.commit()

        salary_columns = [row["name"] for row in conn.execute("PRAGMA table_info(monthly_salary)").fetchall()]
        if "source" not in salary_columns:
            # Defaults to 'manual' so any salary figure that predates
            # auto-detection is treated as user-set and can never be silently
            # overwritten by it.
            conn.execute("ALTER TABLE monthly_salary ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
            conn.commit()

        # Salary is now derived from the largest monthly credit, so the old
        # pattern table has no writer left.
        conn.execute("DROP TABLE IF EXISTS salary_rules")
        conn.commit()

        _migrate_transaction_statuses(conn)
        _migrate_category_rule_patterns(conn)

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


def _migrate_transaction_statuses(conn):
    stale = conn.execute(
        "SELECT 1 FROM bank_transactions WHERE status IN ('pending', 'approved') LIMIT 1"
    ).fetchone()
    if not stale:
        return
    # 'approved' rows already have their expense row linked via expense_id, so
    # this is a pure rename — materialize_expenses skips 'imported'. 'pending'
    # rows become candidates but nothing is created until an explicit backfill.
    conn.execute("UPDATE bank_transactions SET status = 'imported' WHERE status = 'approved'")
    conn.execute("UPDATE bank_transactions SET status = 'new' WHERE status = 'pending'")
    conn.execute(
        "UPDATE bank_transactions SET ignore_reason = 'legacy' WHERE status = 'ignored' AND ignore_reason IS NULL"
    )
    conn.commit()


def _migrate_category_rule_patterns(conn):
    """Normalizes stored patterns and drops duplicates (newest wins) so the
    unique index below can be created. Must run before it — CREATE UNIQUE INDEX
    fails on existing dupes and would take init_db down with it."""
    rows = conn.execute("SELECT id, pattern FROM category_rules ORDER BY id").fetchall()
    seen = {}
    for row in rows:
        normalized = normalize_pattern(row["pattern"])
        if normalized != row["pattern"]:
            conn.execute("UPDATE category_rules SET pattern = ? WHERE id = ?", (normalized, row["id"]))
        if normalized in seen:
            conn.execute("DELETE FROM category_rules WHERE id = ?", (seen[normalized],))
        seen[normalized] = row["id"]
    conn.execute("DELETE FROM category_rules WHERE pattern = ''")
    conn.commit()
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_category_rules_pattern ON category_rules(pattern)"
    )
    conn.commit()


def normalize_pattern(text: str) -> str:
    """Lowercased, whitespace-collapsed. Bank counterparties arrive with runs of
    spaces ('APPLE.COM/BILL         CORK') and inconsistent casing, so both
    stored patterns and the text they're matched against go through this —
    otherwise a perfectly correct pattern silently never matches."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def bucket_month(date_str: str) -> str:
    """Maps a 'YYYY-MM-DD' date to its billing-cycle month: day >= 10 stays in
    that calendar month, day < 10 shifts back one month. Matches how a credit
    card statement actually works — a charge on the 1st isn't "this month's"
    spending, it's still riding the previous cycle, which closes on the 10th."""
    year, month, day = int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10])
    if day < 10:
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return f"{year:04d}-{month:02d}"


def month_window(month: str) -> tuple[str, str]:
    """Returns (start, end) 'YYYY-MM-DD' strings — the half-open date range
    [start, end) whose every date buckets to `month` via bucket_month(). E.g.
    month_window('2026-08') == ('2026-08-10', '2026-09-10')."""
    year, mon = int(month[:4]), int(month[5:7])
    start = f"{year:04d}-{mon:02d}-10"
    if mon == 12:
        end_year, end_mon = year + 1, 1
    else:
        end_year, end_mon = year, mon + 1
    end = f"{end_year:04d}-{end_mon:02d}-10"
    return start, end


def current_bucket_month() -> str:
    return bucket_month(date.today().isoformat())


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


def set_salary_for_month(conn, month: str, amount: float, source: str = "manual"):
    """source='auto' will not overwrite a row the user set by hand — the WHERE
    on the upsert makes that a single statement rather than a read-then-write
    that could race."""
    if source == "auto":
        conn.execute(
            """
            INSERT INTO monthly_salary (month, amount, source) VALUES (?, ?, 'auto')
            ON CONFLICT(month) DO UPDATE SET amount = excluded.amount
            WHERE monthly_salary.source = 'auto'
            """,
            (month, amount),
        )
        return
    conn.execute(
        """
        INSERT INTO monthly_salary (month, amount, source) VALUES (?, ?, 'manual')
        ON CONFLICT(month) DO UPDATE SET amount = excluded.amount, source = 'manual'
        """,
        (month, amount),
    )


def get_salary_source_for_month(conn, month: str):
    row = conn.execute(
        "SELECT source FROM monthly_salary WHERE month <= ? ORDER BY month DESC LIMIT 1",
        (month,),
    ).fetchone()
    return row["source"] if row else None


def clear_salary_for_month(conn, month: str):
    conn.execute("DELETE FROM monthly_salary WHERE month = ?", (month,))


def sync_rent(conn):
    category = conn.execute(
        "SELECT id FROM categories WHERE name = ?", (RENT_CATEGORY_NAME,)
    ).fetchone()
    if not category:
        return

    for month in months_between(RENT_START_MONTH, current_bucket_month()):
        already = conn.execute("SELECT 1 FROM rent_generated WHERE month = ?", (month,)).fetchone()
        if already:
            continue
        # Dated on the 10th (the window's own start) so it buckets into this
        # exact month rather than shifting back a month under bucket_month().
        cur = conn.execute(
            "INSERT INTO expenses (amount, category_id, date, note, is_rent) VALUES (?, ?, ?, 'Rent', 1)",
            (RENT_AMOUNT, category["id"], f"{month}-10"),
        )
        conn.execute(
            "INSERT INTO rent_generated (month, expense_id) VALUES (?, ?)",
            (month, cur.lastrowid),
        )
    conn.commit()
