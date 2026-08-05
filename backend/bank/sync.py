import json
from datetime import date, datetime, timezone
from typing import List, Optional

from bank import crypto
from bank.classify import CREDIT_CARD_COMPANY_IDS, classify_settlement, classify_transaction
from bank.errors import BankAuthError, BankConfigError, BankFetchError
from bank.psd2 import Psd2Client
from bank.rules import suggest_category
from bank.salary import match_salary_rule
from bank.scraper import ScraperClient
from bank.types import NormalizedTxn
from db import bucket_month, month_window, set_salary_for_month


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_psd2(connection, date_from: str, date_to: str) -> List[NormalizedTxn]:
    secrets = json.loads(crypto.decrypt(connection["secrets_enc"]))
    client = Psd2Client()
    return client.fetch_transactions(
        account_ref=connection["account_ref"],
        consent_id=connection["consent_id"],
        access_token=secrets["access_token"],
        date_from=date_from,
        date_to=date_to,
    )


def _fetch_scraper(conn, connection, date_from: str) -> tuple[List[NormalizedTxn], List[NormalizedTxn]]:
    secrets = json.loads(crypto.decrypt(connection["secrets_enc"]))
    client = ScraperClient()
    result = client.sync_login(
        credentials=secrets["credentials"],
        start_date=date_from,
        device_trust_data=secrets.get("device_trust_data"),
        company_id=connection["company_id"],
    )

    if result.get("device_trust_data"):
        secrets["device_trust_data"] = result["device_trust_data"]
        conn.execute(
            "UPDATE bank_connections SET secrets_enc = ? WHERE id = ?",
            (crypto.encrypt(json.dumps(secrets)), connection["id"]),
        )
        conn.commit()

    account_ref = connection["account_ref"]
    txns_by_account = result["transactions_by_account"]
    card_itemized_by_account = result.get("card_itemized_by_account", {})
    if account_ref and account_ref in txns_by_account:
        return txns_by_account[account_ref], card_itemized_by_account.get(account_ref, [])
    # No account_ref pinned yet (first sync) — take the first account and
    # persist it so subsequent syncs are pinned to the same one.
    if not account_ref and txns_by_account:
        first_ref = next(iter(txns_by_account))
        conn.execute(
            "UPDATE bank_connections SET account_ref = ? WHERE id = ?",
            (first_ref, connection["id"]),
        )
        conn.commit()
        return txns_by_account[first_ref], card_itemized_by_account.get(first_ref, [])
    return [], []


def _has_active_credit_card_connection(conn, exclude_connection_id: int) -> bool:
    placeholders = ",".join("?" * len(CREDIT_CARD_COMPANY_IDS))
    row = conn.execute(
        f"""
        SELECT 1 FROM bank_connections
        WHERE status = 'valid' AND id != ? AND company_id IN ({placeholders})
        LIMIT 1
        """,
        (exclude_connection_id, *CREDIT_CARD_COMPANY_IDS),
    ).fetchone()
    return row is not None


def _has_itemized_charge_for_debit_date(conn, connection_id: int, value_date: Optional[str]) -> bool:
    if not value_date:
        return False
    row = conn.execute(
        "SELECT 1 FROM bank_transactions WHERE connection_id = ? AND kind = 'credit_card_charge' AND value_date = ? LIMIT 1",
        (connection_id, value_date),
    ).fetchone()
    return row is not None


def has_matching_cross_connection_charge(conn, row) -> bool:
    """True if this bank_transactions row has a same-amount, close-date
    counterpart from a DIFFERENT connection — signals the same purchase was
    likely imported twice: once itemized via the card connection, once as
    its own line on the bank feed (only happens for immediate-settling
    charges; the bulk lump sum is already handled by the name-fragment
    match in classify_transaction)."""
    if row["kind"] == "credit_card_charge" and row["settlement"] == "immediate":
        anchor_date, other_kind, other_date_col = row["value_date"], "bank_transfer", "booking_date"
    elif row["kind"] == "bank_transfer":
        anchor_date, other_kind, other_date_col = row["booking_date"], "credit_card_charge", "value_date"
    else:
        return False
    if not anchor_date:
        return False
    match = conn.execute(
        f"""
        SELECT 1 FROM bank_transactions
        WHERE connection_id != ? AND kind = ?
          AND (kind != 'credit_card_charge' OR settlement = 'immediate')
          AND amount = ? AND {other_date_col} IS NOT NULL
          AND ABS(julianday({other_date_col}) - julianday(?)) <= 3
        LIMIT 1
        """,
        (row["connection_id"], other_kind, row["amount"], anchor_date),
    ).fetchone()
    return match is not None


def store_transactions(
    conn, connection_id: int, txns: List[NormalizedTxn], company_id: Optional[str] = None,
    force_kind: Optional[str] = None, force_settlement: Optional[str] = None,
    target_month: Optional[str] = None,
) -> dict:
    """Dedupe-insert NormalizedTxns into bank_transactions. Shared by sync_bank_transactions
    and the scraper's connect flow (which already has a batch of txns from its first login).

    target_month, when given, silently discards any txn whose booking_date
    doesn't bucket into that month — a sync scoped to one month shouldn't
    stash unrelated months' data just because the scraper had to fetch a
    wider range to reach it (it has no way to stop fetching at an end date)."""
    inserted = 0
    for txn in txns:
        if target_month and bucket_month(txn.booking_date) != target_month:
            continue
        kind = force_kind or classify_transaction(txn.counterparty, txn.description, company_id)
        settlement = force_settlement or classify_settlement(txn.booking_date, txn.value_date)
        if txn.amount > 0:
            if kind == "bank_transfer" and match_salary_rule(conn, txn.counterparty):
                status = "salary"
                set_salary_for_month(conn, txn.booking_date[:7], txn.amount)
            elif kind == "bank_transfer":
                # Unrecognized incoming bank credit — let the user confirm/ignore
                # or mark it as a salary source in the review UI.
                status = "pending"
            else:
                status = "ignored"  # card-side credits (refunds etc.)
        elif kind == "credit_card_payment" and (
            _has_active_credit_card_connection(conn, connection_id)
            or _has_itemized_charge_for_debit_date(conn, connection_id, txn.value_date)
        ):
            # Same spending as the itemized credit_card_charge rows from the card
            # connection (or from itemized data on this same connection) — counting
            # both would double it.
            status = "ignored"
        else:
            status = "pending"
        category_id = suggest_category(conn, txn)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO bank_transactions
                (connection_id, external_id, booking_date, value_date, amount, currency,
                 counterparty, description, raw_json, status, kind, settlement, suggested_category_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                connection_id, txn.external_id, txn.booking_date, txn.value_date, txn.amount,
                txn.currency, txn.counterparty, txn.description, json.dumps(txn.raw),
                status, kind, settlement, category_id, _now(),
            ),
        )
        if cur.rowcount:
            inserted += 1
    conn.commit()
    return {"fetched": len(txns), "inserted": inserted, "skipped": len(txns) - inserted}


def store_card_itemized_transactions(
    conn, connection_id: int, card_itemized_txns: List[NormalizedTxn], company_id: Optional[str] = None,
    target_month: Optional[str] = None,
) -> dict:
    """Splits Hapoalim's own itemized card charges by origin (set on t.raw by
    _map_card_itemized_transaction) — national (1) always rides the bulk
    cycle, international (2) settles fast, known for certain from the bank's
    own API rather than guessed from date comparison — and stores each half
    with its settlement forced accordingly. Shared by the initial-connect
    flow and sync_bank_transactions."""
    national_txns = [t for t in card_itemized_txns if t.raw.get("origin") == 1]
    international_txns = [t for t in card_itemized_txns if t.raw.get("origin") == 2]
    national_result = store_transactions(
        conn, connection_id, national_txns, company_id,
        force_kind="credit_card_charge", force_settlement="delayed", target_month=target_month,
    )
    international_result = store_transactions(
        conn, connection_id, international_txns, company_id,
        force_kind="credit_card_charge", force_settlement="immediate", target_month=target_month,
    )
    return {
        "fetched": national_result["fetched"] + international_result["fetched"],
        "inserted": national_result["inserted"] + international_result["inserted"],
        "skipped": national_result["skipped"] + international_result["skipped"],
    }


def sync_bank_transactions(conn, connection_id: int, month: str) -> dict:
    connection = conn.execute(
        "SELECT * FROM bank_connections WHERE id = ?", (connection_id,)
    ).fetchone()
    if not connection:
        raise BankConfigError(f"no bank_connections row with id {connection_id}")

    date_from, _ = month_window(month)
    date_to = date.today().isoformat()

    try:
        if connection["provider"] == "psd2":
            txns = _fetch_psd2(connection, date_from, date_to)
            card_itemized_txns = []
        elif connection["provider"] == "scraper":
            txns, card_itemized_txns = _fetch_scraper(conn, connection, date_from)
        else:
            raise BankConfigError(f"unknown provider {connection['provider']}")
    except (BankAuthError, BankFetchError, BankConfigError) as e:
        conn.execute(
            "UPDATE bank_connections SET status = 'error', last_error = ? WHERE id = ?",
            (str(e), connection_id),
        )
        conn.commit()
        raise

    # Itemized charges must be inserted first so the bulk credit_card_payment
    # line's auto-ignore check (_has_itemized_charge_for_debit_date) can find them.
    itemized_result = store_card_itemized_transactions(
        conn, connection_id, card_itemized_txns, connection["company_id"], target_month=month
    )
    regular_result = store_transactions(conn, connection_id, txns, connection["company_id"], target_month=month)
    result = {
        "fetched": itemized_result["fetched"] + regular_result["fetched"],
        "inserted": itemized_result["inserted"] + regular_result["inserted"],
        "skipped": itemized_result["skipped"] + regular_result["skipped"],
    }

    conn.execute(
        "UPDATE bank_connections SET status = 'valid', last_synced_at = ?, last_error = NULL WHERE id = ?",
        (_now(), connection_id),
    )
    conn.commit()

    return result
