import json
from datetime import date, datetime, timezone
from typing import List, Optional

from bank import crypto
from bank.classify import classify_settlement, classify_transaction
from bank.errors import BankAuthError, BankConfigError, BankFetchError
from bank.importer import materialize_expenses
from bank.psd2 import Psd2Client
from bank.scraper import ScraperClient
from bank.types import NormalizedTxn
from db import bucket_month, month_window


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


def store_transactions(
    conn, connection_id: int, txns: List[NormalizedTxn], company_id: Optional[str] = None,
    force_kind: Optional[str] = None, force_settlement: Optional[str] = None,
    target_month: Optional[str] = None,
) -> dict:
    """Stage NormalizedTxns into bank_transactions as status='new'. Pure writer —
    whether a row becomes an expense is decided later by
    bank.importer.materialize_expenses, which sees every row at once instead of
    one at a time mid-insert.

    target_month, when given, silently discards any txn whose booking_date
    doesn't bucket into that month — a sync scoped to one month shouldn't
    stash unrelated months' data just because the scraper had to fetch a
    wider range to reach it (it has no way to stop fetching at an end date)."""
    inserted = 0
    for txn in txns:
        if target_month and bucket_month(txn.booking_date) != target_month:
            continue
        settlement = force_settlement or classify_settlement(txn.booking_date, txn.value_date)
        kind = force_kind or classify_transaction(txn.counterparty, txn.description, company_id, settlement)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO bank_transactions
                (connection_id, external_id, booking_date, value_date, amount, currency,
                 counterparty, description, raw_json, status, kind, settlement, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
            """,
            (
                connection_id, txn.external_id, txn.booking_date, txn.value_date, txn.amount,
                txn.currency, txn.counterparty, txn.description, json.dumps(txn.raw),
                kind, settlement, _now(),
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

    itemized_result = store_card_itemized_transactions(
        conn, connection_id, card_itemized_txns, connection["company_id"], target_month=month
    )
    regular_result = store_transactions(conn, connection_id, txns, connection["company_id"], target_month=month)
    result = {
        "fetched": itemized_result["fetched"] + regular_result["fetched"],
        "inserted": itemized_result["inserted"] + regular_result["inserted"],
        "skipped": itemized_result["skipped"] + regular_result["skipped"],
    }
    result.update(materialize_expenses(conn, month))

    conn.execute(
        "UPDATE bank_connections SET status = 'valid', last_synced_at = ?, last_error = NULL WHERE id = ?",
        (_now(), connection_id),
    )
    conn.commit()

    return result
