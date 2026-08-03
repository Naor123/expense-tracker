from bank.classify import classify_settlement, classify_transaction


def test_credit_card_company_charge_is_always_credit_card_charge():
    assert classify_transaction("Super-Pharm", "groceries", "max") == "credit_card_charge"
    assert classify_transaction(None, None, "max") == "credit_card_charge"


def test_bank_transaction_matching_card_company_name_is_credit_card_payment():
    assert classify_transaction("מקס איט פיננס", None, "hapoalim") == "credit_card_payment"
    assert classify_transaction("MAX", None, "hapoalim") == "credit_card_payment"
    assert classify_transaction("ISRACARD LTD", None, "hapoalim") == "credit_card_payment"
    assert classify_transaction(None, "כאל", "hapoalim") == "credit_card_payment"


def test_ordinary_bank_transaction_is_bank_transfer():
    assert classify_transaction("Bezeq Internet", "ISP monthly bill", "hapoalim") == "bank_transfer"
    assert classify_transaction("John Doe", "rent transfer", "hapoalim") == "bank_transfer"


def test_settlement_within_same_month_is_immediate():
    assert classify_settlement("2026-07-24", "2026-07-27") == "immediate"


def test_settlement_crossing_into_next_month_is_delayed():
    assert classify_settlement("2026-07-11", "2026-08-09") == "delayed"


def test_settlement_with_no_value_date_is_immediate():
    assert classify_settlement("2026-07-11", None) == "immediate"
