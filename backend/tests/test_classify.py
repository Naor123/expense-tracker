from bank.classify import classify_transaction


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
