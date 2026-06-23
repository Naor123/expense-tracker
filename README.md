# Expense Tracker

A household expense tracker: log expenses by category, see a monthly pie-chart breakdown, set up recurring bills that auto-generate every month, track your net salary per month, and optionally email yourself a monthly insight summary.

## Stack

- **Backend**: FastAPI + Python 3.12, raw `sqlite3` (no ORM)
- **Frontend**: React 19 + Vite, `recharts` for the pie chart, `lucide-react` icons

## Features

- Add expenses with amount, category, date, and an optional note
- Categories are editable (rename/delete/add new ones) from the gear icon
- Monthly pie chart of spending by category, with a collapsible "Recurring Bills" / "Other Expenses" list
- Recurring bills (rent, subscriptions, etc.) auto-generate as expenses every month — monthly or every-2-months (odd/even) schedules supported, editable price with "this month only" vs "this month + all past months" options
- Net salary tracked per month (carries forward until you change it again) — edit it from the gear icon
- One-click "email me this month's insight" button (total spent, salary, remaining/over-budget %, category breakdown) — optional, requires email setup below

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

Edit `backend/.env`:

```
DB_PATH=expenses.db
MONTHLY_SALARY=13000
SMTP_USER=
SMTP_APP_PASSWORD=
RECIPIENT_EMAIL=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

- `MONTHLY_SALARY` is just a fallback default — you can set/override your real salary per month from the app's gear icon instead.
- `SMTP_USER` / `SMTP_APP_PASSWORD` / `RECIPIENT_EMAIL` are **only needed if you want the "email me an insight" button to work**. Leave them blank to skip email entirely — everything else works fine without it.

To enable email (Gmail):
1. Turn on 2-Step Verification: https://myaccount.google.com/security
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Put your Gmail address in `SMTP_USER` and `RECIPIENT_EMAIL`, and the 16-character app password (no spaces) in `SMTP_APP_PASSWORD`

Run the backend:

```bash
uvicorn main:app --reload --port 8000
```

It'll create `expenses.db` and seed default categories on first run.

### 2. Frontend

```bash
cd frontend
npm install
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
npm run dev
```

Open http://localhost:5173.

## Notes

- The backend ships with some example seed data (a few household categories and recurring bills). Edit or delete them from the app — gear icon for categories/salary, the repeat icon for recurring bills.
- `backend/.env` and `frontend/.env` are gitignored — never commit real credentials.
