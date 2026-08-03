# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Backend (`backend/`, Python 3.12, venv at `backend/.venv`):
```
backend\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Backend tests (pytest, covers `bank/` only so far): `cd backend && .venv\Scripts\python.exe -m pytest tests/ -v`. No linter configured for the backend.

Mock PSD2 ASPSP (for exercising the bank connector without real bank credentials): `cd backend && uvicorn bank.mock_server:app --port 8010`, then set `PSD2_BASE_URL=http://localhost:8010` in `backend/.env`.

Frontend (`frontend/`, React 19 + Vite):
```
npm install
npm run dev        # http://localhost:5173
npm run build
npm run lint        # eslint .
```
No test suite configured for the frontend.

Both dev servers are normally started in separate visible terminal windows (`Start-Process cmd -ArgumentList "/k ..."`), not as background tasks, and are typically already running during development — check before starting new ones.

## Architecture

Two independent processes, no shared code: `backend/` (FastAPI + raw `sqlite3`) and `frontend/` (React 19 + Vite). The frontend talks to the backend over HTTP using `VITE_API_URL` (`frontend/.env`) as the base URL; backend `DB_PATH` (`backend/.env`, default `expenses.db`) points at the SQLite file.

**Backend** — no ORM, parameterized SQL only, Pydantic v2 for all request/response shapes (`models.py`), errors raised via `HTTPException`. `db.py` owns the schema (`init_db`) and seed data; `main.py` holds every route. Each request opens and closes its own `sqlite3` connection (`get_connection()`) — there's no connection pooling or shared session.

Schema:
- `categories(id, name, color)` — seeded idempotently by name (`INSERT ... WHERE NOT EXISTS`), so re-running `init_db()` is safe even after the table already has rows, and new seed categories can be added later without wiping existing ones.
- `expenses(id, amount, category_id, date, note, recurring_id)` — `date` is stored as `YYYY-MM-DD` text; month filtering everywhere uses `date LIKE 'YYYY-MM-%'`.
- `recurring_bills(id, name, amount, category_id, interval_months, month_parity, start_month, active)` — `interval_months` is 1 (monthly) or 2 (bimonthly); when 2, `month_parity` (`'odd'`/`'even'`) picks which calendar months it applies to (odd = Jan/Mar/May/Jul/Sep/Nov). Seeded idempotently by name, same pattern as categories.
- `recurring_generated(recurring_id, month, expense_id)` — tracks which `(bill, month)` pairs have already produced an expense, so generation is idempotent and a user-deleted generated expense is never silently recreated.
- `monthly_salary(month, amount)` — one row per month the user has explicitly set via the UI. `get_salary_for_month(conn, month)` in `db.py` resolves a month's salary by taking the most recent row with `month <= requested month` (carry-forward, so setting it once covers future months until changed again); if there's no row at all yet, it falls back to the `MONTHLY_SALARY` env var.

**Recurring bill generation**: `sync_recurring_bills(conn)` in `db.py` walks every active recurring bill from its `start_month` through the current real calendar month (`months_between` + `bill_applies_to_month`), and inserts an expense for any month not already present in `recurring_generated`. This runs at FastAPI startup and again at the top of `GET /expenses`, `GET /summary`, and `GET /months` — so the generated set is always caught up to "now" on read, with no separate scheduler/cron. It's also called once more right after `POST /recurring-bills` to backfill immediately. Deleting a recurring bill (`DELETE /recurring-bills/{id}`) only removes the definition; past generated expenses and their `recurring_generated` rows are intentionally kept (FK enforcement is turned off for just that one DELETE statement, since those child rows must survive).

Category deletion is blocked (409) if it's the last remaining category or if any expense still references it.

**Email insights**: `POST /insights/send-email?month=YYYY-MM` reuses `compute_summary(conn, month)` (the same helper `GET /summary` calls) plus `get_salary_for_month`, then hands off to `backend/mailer.py`'s `send_summary_email(month, summary, salary)` — stdlib `smtplib`/`email.mime` only, no third-party mail dependency. `mailer.py` raises `MailerConfigError` (missing `SMTP_USER`/`SMTP_APP_PASSWORD`/`RECIPIENT_EMAIL`) or `MailerSendError` (SMTP itself failed); `main.py` maps these to 503/502 respectively. A month with no resolvable salary returns 503 before even trying to send.

**Frontend** — functional components + hooks only, one component per file under `src/components/`, no state library. `App.jsx` is the single source of truth: holds `month`, `categories`, `expenses`, `summary`, `recurringBills`, `salary` state and all the `handle*` mutator functions, passed down as props; components call back up rather than fetching independently. `api.js` is a thin axios wrapper, one exported function per endpoint. Colors are CSS variables in `index.css` (`:root` for light, `[data-theme='dark']` for dark) — components never hardcode hex values except where a category's own stored `color` is applied inline (e.g. color dots, pie slices). Theme is persisted to `localStorage` and applied via `document.documentElement.setAttribute('data-theme', ...)`.

`CategoryManager.jsx` (opened via the header's `Settings` icon) doubles as the general settings modal — it holds both category CRUD and the Net Salary inline editor (`salary`/`onUpdateSalary` props), not just categories despite the filename. The header also has a `Repeat` icon (opens `RecurringBillsManager`) and a `Mail` icon (`handleSendInsightsEmail` — fire-and-forget, feedback shown via a transient banner under the header using the shared `success-banner`/`error-banner` classes).

Note: `expense-list[hidden]` needs an explicit `display: none` override in `index.css` — the `.expense-list { display: flex }` class rule otherwise beats the `[hidden]` attribute's default styling.

**Bank connector (`backend/bank/`)** — imports transactions from Bank Hapoalim instead of manual entry. Two interchangeable providers implement the same `BankProvider` protocol (`bank/base.py`), selected via `BANK_PROVIDER` env var and both normalizing to `NormalizedTxn` (`bank/types.py`):
- `bank/psd2.py` — a Berlin Group AIS client for the Bank of Israel's NextGenPSD2 profile (OAuth SCA approach only — the spec's plain `scaRedirect` link is commented out, so authorization is consent → `scaOAuth` link → OAuth2 Authorization Server Metadata → standard authorization-code redirect → `/bank/callback` → token exchange → Bearer-authenticated AIS calls). **Requires a Capital Markets Authority TPP license for production credentials** — Hapoalim will not issue `client_id`/mTLS certs to an individual for personal use. `bank/mock_server.py` is a standalone FastAPI ASPSP replaying the spec's own examples so the whole flow is testable without real credentials.
- `bank/scraper.py` + `bank/sidecar/` — shells out to the Node `israeli-bank-scrapers` package (`bank/sidecar/scrape.mjs`) to log into Hapoalim's own web banking with real credentials and scrape transactions. Works today with your real account; no licensing needed since it's not a PSD2 TPP integration, but it depends on the bank's website not changing and is subject to Hapoalim's own terms of use.

New tables (`db.py`): `bank_connections` (one row per connected account, `secrets_enc` is a Fernet blob keyed by `BANK_ENC_KEY` holding tokens or scraper credentials), `bank_transactions` (staging table, `UNIQUE(connection_id, external_id)` makes re-syncing an overlapping date range a no-op — same idempotency role `recurring_generated` plays for recurring bills), `category_rules` (substring-match merchant→category rules, checked by `bank/rules.py:suggest_category`). `expenses` gained a `bank_txn_id` column (via the same `PRAGMA table_info` migration guard as `recurring_id`).

**Sync is explicit, never on-read** — unlike `sync_recurring_bills`, `bank/sync.py:sync_bank_transactions` is only invoked from `POST /bank/sync`. It does real network I/O and BOI's spec caps unattended AIS access at a fixed `frequencyPerDay: 100`, so wiring it into `GET /expenses` like the recurring-bill sync would be both slow and a rate-limit risk.

Imported transactions land in `bank_transactions` with `status='pending'` (credits are auto-`ignored` so salary/refunds never become expenses) and require review via `POST /bank/transactions/{id}/approve` (or `/ignore`, or bulk-approve) before becoming a real row in `expenses` — this is deliberate, since the recurring-bill generator already creates expenses for bills like Rent/Arnona/Gym, and auto-inserting the bank's version of those would double-count them. `GET /bank/transactions` flags `possible_duplicate` when a pending transaction's amount matches an active recurring bill for that month (reuses `db.py:bill_applies_to_month`).

Frontend: `BankConnectModal.jsx` (connections list + connect form; opens a blank popup synchronously on click and only sets its `location.href` after the `await onConnect(...)` resolves, since setting it after the await in one step gets popup-blocked) and `ImportReviewModal.jsx` (pending-transaction review, opened from the header's `Inbox` icon which shows a pending-count badge). `ExpenseList.jsx` groups by `bank_txn_id` into a third "Imported from Bank" section alongside Recurring/Other.
