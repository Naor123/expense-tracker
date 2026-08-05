from bank.classify import classify_settlement, classify_transaction


def test_credit_card_company_charge_is_always_credit_card_charge():
    assert classify_transaction("Super-Pharm", "groceries", "max", "immediate") == "credit_card_charge"
    assert classify_transaction(None, None, "max", "delayed") == "credit_card_charge"


def test_bank_transaction_matching_card_company_name_and_delayed_is_credit_card_payment():
    assert classify_transaction("מקס איט פיננס", None, "hapoalim", "delayed") == "credit_card_payment"
    assert classify_transaction("MAX", None, "hapoalim", "delayed") == "credit_card_payment"
    assert classify_transaction("ISRACARD LTD", None, "hapoalim", "delayed") == "credit_card_payment"
    assert classify_transaction(None, "כאל", "hapoalim", "delayed") == "credit_card_payment"


def test_bank_transaction_matching_card_company_name_but_immediate_is_bank_transfer():
    # Same-day settlement means it's an individual foreign-currency purchase
    # labeled with the card network's name, not the once-a-month bulk payment.
    assert classify_transaction("מסטרקרד", None, "hapoalim", "immediate") == "bank_transfer"
    assert classify_transaction("MAX", None, "hapoalim", "immediate") == "bank_transfer"


def test_ordinary_bank_transaction_is_bank_transfer():
    assert classify_transaction("Bezeq Internet", "ISP monthly bill", "hapoalim", "immediate") == "bank_transfer"
    assert classify_transaction("John Doe", "rent transfer", "hapoalim", "delayed") == "bank_transfer"


def test_settlement_within_same_month_is_immediate():
    assert classify_settlement("2026-07-24", "2026-07-27") == "immediate"


def test_settlement_crossing_into_next_month_is_delayed():
    assert classify_settlement("2026-07-11", "2026-08-09") == "delayed"


def test_settlement_with_no_value_date_is_immediate():
    assert classify_settlement("2026-07-11", None) == "immediate"


def test_late_month_purchase_settling_on_the_9th_or_10th_is_delayed_even_within_the_same_month():
    # Bought Aug 1, cycle closes Aug 10 -- both August, so a pure month
    # comparison misses that this rides the same bulk cycle as everything else.
    assert classify_settlement("2026-08-01", "2026-08-10") == "delayed"
    assert classify_settlement("2026-08-03", "2026-08-09") == "delayed"


def test_short_gap_settlement_near_the_9th_is_still_immediate_if_not_exactly_on_it():
    assert classify_settlement("2026-07-06", "2026-07-08") == "immediate"


def test_same_day_settlement_on_the_9th_is_immediate_not_delayed():
    # A plain bank_transfer's booking_date == value_date is a coincidence of
    # calendar, not a sign it's riding the card cycle -- there's no gap at all.
    assert classify_settlement("2026-07-09", "2026-07-09") == "immediate"
