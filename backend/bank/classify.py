from bank.companies import SCRAPER_COMPANIES

# Companies scraped as their own credit-card connection (itemized purchases).
# When one of these is what generated the transaction, it's a real charge.
CREDIT_CARD_COMPANY_IDS = {cid for cid, c in SCRAPER_COMPANIES.items() if c["kind"] == "credit_card"}

# Name fragments identifying a credit-card company's own monthly lump-sum debit
# on a BANK account's feed — this is the same money as the itemized purchases
# from a connected card company, just as one rolled-up line, so it must be told
# apart from an actual transfer/standing order/check.
CREDIT_CARD_COMPANY_NAME_FRAGMENTS = [
    "מקס", "max",
    "ישראכרט", "isracard",
    "כאל", "visa cal",  # "cal" alone is too generic (matches "local", "medical", ...)
    "לאומי קארד", "leumi card",
    "אמריקן אקספרס", "amex", "american express",
    "מסטרקרד", "מאסטרקארד", "mastercard",
]


def classify_transaction(counterparty: str, description: str, company_id: str) -> str:
    """Returns 'credit_card_charge' (itemized purchase from a card connection),
    'credit_card_payment' (a bank account's lump-sum debit to a card company —
    the same spending as credit_card_charge rows, just unitemized), or
    'bank_transfer' (everything else on a bank account: transfers, standing
    orders, checks, direct debits).

    A name-fragment match on a BANK account's feed is unambiguously the bulk
    lump-sum payment: an individual purchase never reaches this account feed
    carrying a card-network label -- it only ever shows up itemized, via the
    connected card company (credit_card_charge above) or, for the bank's own
    card, the itemized-charges feed (force_kind, see bank.sync), never through
    this classifier. This used to require settlement == 'delayed' as well, on
    the theory that a same-day match was an individual purchase merely labeled
    with the network name -- but on the real Hapoalim feed the bulk line's
    value_date always equals its booking_date (there's no settlement gap to
    observe at all, despite the real-world cycle settling around the 10th),
    so that condition only ever produced false negatives and let genuine bulk
    lines slip past the card_lump_sum dedup as brand new, double-counted
    expenses."""
    if company_id in CREDIT_CARD_COMPANY_IDS:
        return "credit_card_charge"

    haystack = f"{counterparty or ''} {description or ''}".lower()
    if any(fragment.lower() in haystack for fragment in CREDIT_CARD_COMPANY_NAME_FRAGMENTS):
        return "credit_card_payment"

    return "bank_transfer"


def classify_settlement(booking_date: str, value_date: str | None) -> str:
    """Returns 'immediate' (settles within days — typically foreign-currency
    purchases) or 'delayed' (rides the card company's ~9th/10th-of-next-month
    lump sum).

    Purely comparing calendar months doesn't work: a purchase made late enough
    in the month rides the bulk cycle even though its booking_date and
    value_date land in the *same* calendar month (e.g. bought Aug 1, cycle
    closes Aug 10 — both August); conversely, a genuinely fast-settling charge
    booked right at month-end (e.g. Aug 30) can have a value_date that rolls
    into the 1st of the next month — a 1-2 day lag, not a delayed cycle, that
    a naive "month changed" check would wrongly call delayed. The reliable
    signal turned out to be value_date's day-of-month itself: every observed
    delayed charge settles on the 9th or 10th (the cycle's close, shifted a
    day for weekends/holidays), and no genuinely fast-settling charge ever
    lands there — whichever month it's the 9th/10th *of*.

    That day check only applies when there's an actual settlement gap —
    booking_date == value_date (true of every plain bank_transfer row; there's
    no card cycle to ride) stays 'immediate' even if that shared date happens
    to be the 9th or 10th, which is coincidence, not signal."""
    if not value_date or value_date == booking_date:
        return "immediate"
    return "delayed" if value_date[8:10] in ("09", "10") else "immediate"
