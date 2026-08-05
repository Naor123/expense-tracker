from bank.scraper import _local_date, _map_transaction


def test_local_date_converts_israel_midnight_from_utc():
    # The scraper serializes Israel-local midnight to UTC before handing it to
    # Python; a naive [:10] slice reads the UTC calendar day, which is always
    # one day behind the real Israel date. This is that exact shape of value.
    assert _local_date("2026-08-01T21:00:00.000Z") == "2026-08-02"


def test_local_date_handles_israel_standard_time_offset():
    # Winter (IST, UTC+2) shifts the UTC boundary by an hour vs. summer (IDT,
    # UTC+3) -- both must resolve to the correct Israel calendar date.
    assert _local_date("2026-01-15T22:00:00.000Z") == "2026-01-16"
    assert _local_date("2026-01-15T21:00:00.000Z") == "2026-01-15"


def test_local_date_handles_missing_value():
    assert _local_date("") == ""


def test_map_transaction_uses_israel_local_date_not_utc_date():
    txn = _map_transaction({
        "identifier": "tx-1",
        "date": "2026-08-01T21:00:00.000Z",
        "processedDate": "2026-08-09T21:00:00.000Z",
        "chargedAmount": -64.0,
        "description": "WOLT",
    })
    assert txn.booking_date == "2026-08-02"
    assert txn.value_date == "2026-08-10"
