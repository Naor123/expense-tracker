from main import compute_summary


def test_pending_settlement_sums_delayed_credit_card_charges_for_the_month(conn, bank_connection):
    conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, created_at)
        VALUES (?, 'tx-delayed', '2026-07-11', '2026-08-09', -250.0, 'ILS', 'Parking', '', '{}',
                'pending', 'credit_card_charge', 'delayed', '2026-07-11')
        """,
        (bank_connection,),
    )
    conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, created_at)
        VALUES (?, 'tx-immediate', '2026-07-24', '2026-07-27', -11.9, 'ILS', 'Apple', '', '{}',
                'pending', 'credit_card_charge', 'immediate', '2026-07-24')
        """,
        (bank_connection,),
    )
    conn.commit()

    summary = compute_summary(conn, "2026-07")
    assert summary["pending_settlement"] == 250.0


def test_pending_settlement_is_zero_with_no_delayed_charges(conn):
    summary = compute_summary(conn, "2026-07")
    assert summary["pending_settlement"] == 0
