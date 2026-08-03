import json
import os
import subprocess
from typing import List, Optional

from bank.config import BankSettings, get_bank_settings
from bank.errors import BankAuthError, BankFetchError
from bank.types import BankAccount, NormalizedTxn

_SIDECAR_DIR = os.path.join(os.path.dirname(__file__), "sidecar")
_SIDECAR_SCRIPT = os.path.join(_SIDECAR_DIR, "scrape.mjs")


class ScraperClient:
    def __init__(self, settings: Optional[BankSettings] = None):
        self.settings = settings or get_bank_settings()

    def _run(self, credentials: dict, start_date: str, otp_code: Optional[str] = None,
              long_term_token: Optional[str] = None) -> dict:
        payload = {
            "companyId": self.settings.scraper_company_id,
            "credentials": credentials,
            "startDate": start_date,
        }
        if otp_code:
            payload["otpCode"] = otp_code
        if long_term_token:
            payload["longTermTwoFactorAuthToken"] = long_term_token

        proc = subprocess.run(
            [self.settings.scraper_node_path, _SIDECAR_SCRIPT],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=_SIDECAR_DIR,
            timeout=180,
        )
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise BankFetchError(f"scraper sidecar produced no output: {proc.stderr[-2000:]}")

        if not result.get("success"):
            raise BankAuthError(
                f"scraper login failed: {result.get('errorType')} {result.get('errorMessage')}"
            )
        return result

    def login_and_fetch(
        self, credentials: dict, start_date: str, otp_code: Optional[str] = None,
        long_term_token: Optional[str] = None,
    ) -> dict:
        """Runs one scrape session; returns {accounts, long_term_token}."""
        result = self._run(credentials, start_date, otp_code, long_term_token)
        accounts = []
        transactions_by_account: dict[str, List[NormalizedTxn]] = {}
        for acc in result.get("accounts", []):
            account_ref = acc.get("accountNumber", "")
            accounts.append(BankAccount(account_ref=account_ref, name=account_ref))
            transactions_by_account[account_ref] = [
                _map_transaction(t) for t in acc.get("txns", []) if t.get("status") == "completed"
            ]
        return {
            "accounts": accounts,
            "transactions_by_account": transactions_by_account,
            "long_term_token": result.get("longTermTwoFactorAuthToken"),
        }


def _map_transaction(t: dict) -> NormalizedTxn:
    identifier = t.get("identifier")
    if not identifier:
        identifier = f"{t.get('date')}-{t.get('chargedAmount')}-{t.get('description')}"
    return NormalizedTxn(
        external_id=str(identifier),
        booking_date=str(t.get("date", ""))[:10],
        value_date=str(t.get("processedDate", ""))[:10] or None,
        amount=float(t.get("chargedAmount", 0)),
        currency="ILS",
        counterparty=t.get("description"),
        description=t.get("memo"),
        raw=t,
    )
