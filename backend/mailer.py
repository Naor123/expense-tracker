import os
import smtplib
from email.mime.text import MIMEText


class MailerConfigError(Exception):
    pass


class MailerSendError(Exception):
    pass


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def format_month_name(month: str) -> str:
    year, month_num = month.split("-")
    return f"{MONTH_NAMES[int(month_num) - 1]} {year}"


def build_email_body(month: str, summary: dict, salary: float) -> tuple[str, str]:
    month_label = format_month_name(month)
    total = summary["total"]
    remaining = salary - total
    percent_used = round((total / salary * 100), 1) if salary else 0

    if remaining >= 0:
        status_line = f"Remaining: ₪{remaining:,.2f} ({percent_used}% of salary spent)"
    else:
        status_line = f"Over budget by: ₪{abs(remaining):,.2f} ({percent_used}% of salary spent)"

    lines = [
        f"Expense Summary — {month_label}",
        "",
        f"Total spent: ₪{total:,.2f}",
        f"Salary: ₪{salary:,.2f}",
        status_line,
        "",
        "By category:",
    ]

    if not summary["categories"]:
        lines.append("  (no expenses recorded)")
    else:
        for cat in summary["categories"]:
            lines.append(f"  - {cat['name']}: ₪{cat['amount']:,.2f} ({cat['percent']}%)")

    subject = f"Expense Insights — {month_label}"
    body = "\n".join(lines)
    return subject, body


def send_summary_email(month: str, summary: dict, salary: float) -> None:
    smtp_user = os.getenv("SMTP_USER")
    smtp_app_password = os.getenv("SMTP_APP_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL")

    missing = [
        name
        for name, val in [
            ("SMTP_USER", smtp_user),
            ("SMTP_APP_PASSWORD", smtp_app_password),
            ("RECIPIENT_EMAIL", recipient),
        ]
        if not val
    ]
    if missing:
        raise MailerConfigError(
            f"Email is not configured. Missing env var(s): {', '.join(missing)}."
        )

    subject, body = build_email_body(month, summary, salary)

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_app_password)
            server.sendmail(smtp_user, [recipient], msg.as_string())
    except Exception as e:
        raise MailerSendError(str(e)) from e
