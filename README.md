# Expense Tracker

A household expense tracker: log expenses by category, see a monthly pie-chart breakdown, set up recurring bills that auto-generate every month, track your net salary per month, and optionally email yourself a monthly insight summary.

## How to get this running on your computer (no coding knowledge needed)

This app has two parts that need to run on your computer: one called the "backend" (handles the data) and one called the "frontend" (the screen you actually use). The steps below set both of them up. It looks long, but it's mostly just clicking "Next" on a couple of installers — you only have to do this once.

### Step 1: Install two free programs

The app is built with Python and Node.js, so your computer needs both installed.

1. **Python** — go to https://www.python.org/downloads/ and download the latest version.
   - When installing, **make sure to check the box that says "Add python.exe to PATH"** at the bottom of the first screen. This is important — if you skip it, things won't work.
2. **Node.js** — go to https://nodejs.org and download the "LTS" version (the recommended one).
   - Just click Next through the installer with the default options.

If you're not sure whether you already have these, you can skip ahead and try Step 3 (`setup.bat`) — it'll tell you clearly if something's missing.

### Step 2: Download this project

1. On this GitHub page, click the green **"Code"** button, then **"Download ZIP"**.
2. Find the downloaded ZIP file (usually in your Downloads folder) and **extract/unzip it** (right-click it → "Extract All").
3. Open the extracted folder — you should see files like `setup.bat`, `start.bat`, `backend`, `frontend`.

### Step 3: Run the setup

Double-click **`setup.bat`**.

A black window will open and do some work for a minute or two — this installs everything the app needs. When it says "Setup complete!", you're done. (If it shows an error about Python or Node.js not being found, go back to Step 1 and make sure you installed them, then try again.)

### Step 4: Start the app

Double-click **`start.bat`** any time you want to use the app.

Two black windows will open (leave them open — they're what's running the app) and your browser will open automatically to the app. When you're done using it, just close those two black windows.

That's it! You only need to do Step 3 once. From now on, just double-click `start.bat` whenever you want to use the app.

## Optional: the "email me an insight" button

There's a button in the app (the envelope/mail icon) that emails you a summary of your spending for the month. This is **completely optional** — everything else in the app works fine without setting this up.

If you want it to work:

1. Find the `backend` folder, and inside it a file called `.env` — open it with Notepad (right-click → "Open with" → "Notepad").
2. You'll need a Gmail account and an "App Password" for it:
   - Turn on 2-Step Verification: https://myaccount.google.com/security
   - Generate an App Password: https://myaccount.google.com/apppasswords
3. Fill in these three lines in the `.env` file:
   ```
   SMTP_USER=youraddress@gmail.com
   SMTP_APP_PASSWORD=the16characterpasswordfromabove
   RECIPIENT_EMAIL=youraddress@gmail.com
   ```
4. Save the file, then close and reopen the app using `start.bat` again.

## Features

- Add expenses with amount, category, date, and an optional note
- Categories are editable (rename/delete/add new ones) from the gear icon
- Monthly pie chart of spending by category, with a collapsible "Recurring Bills" / "Other Expenses" list
- Recurring bills (rent, subscriptions, etc.) auto-generate as expenses every month — monthly or every-2-months (odd/even) schedules supported, editable price with "this month only" vs "this month + all past months" options
- Net salary tracked per month (carries forward until you change it again) — edit it from the gear icon
- One-click "email me this month's insight" button (total spent, salary, remaining/over-budget %, category breakdown) — optional, see above

The app ships with some example categories and recurring bills already in it — feel free to edit or delete them from the gear icon (categories/salary) and the repeat icon (recurring bills).

---

## For developers

### Stack

- **Backend**: FastAPI + Python 3.12, raw `sqlite3` (no ORM)
- **Frontend**: React 19 + Vite, `recharts` for the pie chart, `lucide-react` icons

### Manual setup (instead of the .bat scripts)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm install
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
npm run dev
```

Open http://localhost:5173. `backend/.env` and `frontend/.env` are gitignored — never commit real credentials.
