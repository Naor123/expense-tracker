import json
from datetime import datetime, timezone
from typing import List

from bank import crypto
from bank.errors import BankAuthError, BankConfigError, BankFetchError
from bank.psd2 import Psd2Client
from bank.rules import suggest_category
from bank.scraper import ScraperClient
from bank.types import NormalizedTxn


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


def _fetch_scraper(conn, connection, date_from: str) -> List[NormalizedTxn]:
    secrets = json.loads(crypto.decrypt(connection["secrets_enc"]))
    client = ScraperClient()
    result = client.sync_login(
        credentials=secrets["credentials"],
        start_date=date_from,
        device_trust_data=secrets.get("device_trust_data"),
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
    if account_ref and account_ref in txns_by_account:
        return txns_by_account[account_ref]
    # No account_ref pinned yet (first sync) — take the first account and
    # persist it so subsequent syncs are pinned to the same one.
    if not account_ref and txns_by_account:
        first_ref = next(iter(txns_by_account))
        conn.execute(
            "UPDATE bank_connections SET account_ref = ? WHERE id = ?",
            (first_ref, connection["id"]),
        )
        conn.commit()
        return txns_by_account[first_ref]
    return []


def store_transactions(conn, connection_id: int, txns: List[NormalizedTxn]) -> dict:
    """Dedupe-insert NormalizedTxns into bank_transactions. Shared by sync_bank_transactions
    and the scraper's connect flow (which already has a batch of txns from its first login)."""
    inserted = 0
    for txn in txns:
        status = "ignored" if txn.amount > 0 else "pending"
        category_id = suggest_category(conn, txn)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO bank_transactions
                (connection_id, external_id, booking_date, value_date, amount, currency,
                 counterparty, description, raw_json, status, suggested_category_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                connection_id, txn.external_id, txn.booking_date, txn.value_date, txn.amount,
                txn.currency, txn.counterparty, txn.description, json.dumps(txn.raw),
                status, category_id, _now(),
            ),
        )
        if cur.rowcount:
            inserted += 1
    conn.commit()
    return {"fetched": len(txns), "inserted": inserted, "skipped": len(txns) - inserted}


def sync_bank_transactions(conn, connection_id: int, date_from: str, date_to: str) -> dict:
    connection = conn.execute(
        "SELECT * FROM bank_connections WHERE id = ?", (connection_id,)
    ).fetchone()
    if not connection:
        raise BankConfigError(f"no bank_connections row with id {connection_id}")

    try:
        if connection["provider"] == "psd2":
            txns = _fetch_psd2(connection, date_from, date_to)
        elif connection["provider"] == "scraper":
            txns = _fetch_scraper(conn, connection, date_from)
        else:
            raise BankConfigError(f"unknown provider {connection['provider']}")
    except (BankAuthError, BankFetchError, BankConfigError) as e:
        conn.execute(
            "UPDATE bank_connections SET status = 'error', last_error = ? WHERE id = ?",
            (str(e), connection_id),
        )
        conn.commit()
        raise

    result = store_transactions(conn, connection_id, txns)

    conn.execute(
        "UPDATE bank_connections SET status = 'valid', last_synced_at = ?, last_error = NULL WHERE id = ?",
        (_now(), connection_id),
    )
    conn.commit()

    return result
