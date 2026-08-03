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
    orders, checks, direct debits)."""
    if company_id in CREDIT_CARD_COMPANY_IDS:
        return "credit_card_charge"

    haystack = f"{counterparty or ''} {description or ''}".lower()
    if any(fragment.lower() in haystack for fragment in CREDIT_CARD_COMPANY_NAME_FRAGMENTS):
        return "credit_card_payment"

    return "bank_transfer"
