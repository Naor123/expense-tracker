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


def test_extra_income_sums_non_salary_credits(conn, bank_connection):
    conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, ignore_reason, created_at)
        VALUES (?, 'tx-miluim', '2026-07-15', '2026-07-15', 1065.0, 'ILS', 'מילואים', '', '{}',
                'ignored', 'bank_transfer', 'immediate', 'incoming_credit', '2026-07-15')
        """,
        (bank_connection,),
    )
    conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, ignore_reason, created_at)
        VALUES (?, 'tx-refund', '2026-07-16', '2026-07-16', 50.0, 'ILS', 'Amazon refund', '', '{}',
                'ignored', 'credit_card_charge', 'immediate', 'card_refund', '2026-07-16')
        """,
        (bank_connection,),
    )
    # The salary winner itself must not double-count as extra income.
    conn.execute(
        """
        INSERT INTO bank_transactions
            (connection_id, external_id, booking_date, value_date, amount, currency,
             counterparty, description, raw_json, status, kind, settlement, created_at)
        VALUES (?, 'tx-salary', '2026-07-14', '2026-07-14', 17146.21, 'ILS', 'Salary', '', '{}',
                'salary', 'bank_transfer', 'immediate', '2026-07-14')
        """,
        (bank_connection,),
    )
    conn.commit()

    summary = compute_summary(conn, "2026-07")
    assert summary["extra_income"] == 1115.0
