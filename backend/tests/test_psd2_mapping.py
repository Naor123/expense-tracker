from bank.psd2 import _map_transaction


def test_maps_debit_transaction_per_boi_schema():
    # Shape per the BOI NextGenPSD2 v1.7 `transactions` schema (creditorName + negative amount = a debit)
    raw = {
        "transactionId": "tx-1001",
        "bookingDate": "2026-07-05",
        "valueDate": "2026-07-05",
        "transactionAmount": {"amount": "-160.00", "currency": "ILS"},
        "creditorName": "Bezeq Internet",
        "remittanceInformationUnstructured": "ISP monthly bill",
    }
    txn = _map_transaction(raw)
    assert txn.external_id == "tx-1001"
    assert txn.booking_date == "2026-07-05"
    assert txn.amount == -160.0
    assert txn.currency == "ILS"
    assert txn.counterparty == "Bezeq Internet"
    assert txn.description == "ISP monthly bill"
    assert txn.raw == raw


def test_maps_credit_transaction_using_debtor_name():
    raw = {
        "transactionId": "tx-1003",
        "bookingDate": "2026-07-10",
        "transactionAmount": {"amount": "12000.00", "currency": "ILS"},
        "debtorName": "Employer Ltd",
        "remittanceInformationUnstructured": "Salary",
    }
    txn = _map_transaction(raw)
    assert txn.amount == 12000.0
    assert txn.counterparty == "Employer Ltd"


def test_falls_back_to_entry_reference_when_no_transaction_id():
    raw = {
        "entryReference": "entry-42",
        "bookingDate": "2026-07-05",
        "transactionAmount": {"amount": "-10.00", "currency": "ILS"},
    }
    txn = _map_transaction(raw)
    assert txn.external_id == "entry-42"


def test_falls_back_to_additional_information_for_description():
    raw = {
        "transactionId": "tx-9",
        "bookingDate": "2026-07-05",
        "transactionAmount": {"amount": "-10.00", "currency": "ILS"},
        "additionalInformation": "POS purchase",
    }
    txn = _map_transaction(raw)
    assert txn.description == "POS purchase"
