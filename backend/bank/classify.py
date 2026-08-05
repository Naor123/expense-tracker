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


def classify_transaction(counterparty: str, description: str, company_id: str, settlement: str) -> str:
    """Returns 'credit_card_charge' (itemized purchase from a card connection),
    'credit_card_payment' (a bank account's lump-sum debit to a card company —
    the same spending as credit_card_charge rows, just unitemized), or
    'bank_transfer' (everything else on a bank account: transfers, standing
    orders, checks, direct debits).

    A name-fragment match only counts as the bulk payment when settlement is
    'delayed' — the once-a-month lump sum really does ride the delayed cycle.
    A same-day (immediate) match against a card network name is an individual
    foreign-currency purchase that happens to be labeled with the network name
    on the account feed, not the bulk payment; treating it as one would
    wrongly auto-ignore a real expense."""
    if company_id in CREDIT_CARD_COMPANY_IDS:
        return "credit_card_charge"

    haystack = f"{counterparty or ''} {description or ''}".lower()
    if settlement == "delayed" and any(fragment.lower() in haystack for fragment in CREDIT_CARD_COMPANY_NAME_FRAGMENTS):
        return "credit_card_payment"

    return "bank_transfer"


def classify_settlement(booking_date: str, value_date: str | None) -> str:
    """Returns 'immediate' (settles within days — typically foreign-currency
    purchases) or 'delayed' (rides the card company's ~10th-of-next-month lump
    sum) based on whether value_date crosses into a later calendar month than
    booking_date."""
    if not value_date:
        return "immediate"
    return "delayed" if value_date[:7] > booking_date[:7] else "immediate"
