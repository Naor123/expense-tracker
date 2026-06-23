# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Backend (`backend/`, Python 3.12, venv at `backend/.venv`):
```
backend\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
No test suite or linter configured for the backend.

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
