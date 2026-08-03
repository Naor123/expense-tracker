import json
import os
import queue
import subprocess
import threading
import time
import uuid
from typing import List, Optional

from bank.config import BankSettings, get_bank_settings
from bank.errors import BankAuthError, BankFetchError
from bank.types import BankAccount, NormalizedTxn

_SIDECAR_DIR = os.path.join(os.path.dirname(__file__), "sidecar")
_SIDECAR_SCRIPT = os.path.join(_SIDECAR_DIR, "scrape.mjs")

_LINE_TIMEOUT_SECONDS = 120
_SESSION_MAX_AGE_SECONDS = 300  # abandoned OTP prompts are reaped on the next login attempt


class _SidecarSession:
    """A running scrape.mjs process paused mid-login, waiting for an OTP code.

    The sidecar is a long-lived subprocess for the duration of one login attempt
    (not one-shot request/response) because Hapoalim's OTP retrieval is an
    interactive callback the library invokes *during* the scrape — the process
    has to stay alive between the "awaitingOtp" line and the code arriving from
    a second, separate HTTP request.
    """

    def __init__(self, settings: BankSettings):
        self.proc = subprocess.Popen(
            [settings.scraper_node_path, _SIDECAR_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",  # Node always writes UTF-8; without this, Windows
            # defaults to the system codepage (cp1252) and Hebrew merchant/memo
            # text in real transactions breaks decoding.
            bufsize=1,
            cwd=_SIDECAR_DIR,
        )
        self.created_at = time.monotonic()
        self._lines: "queue.Queue[str]" = queue.Queue()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self):
        for line in self.proc.stdout:
            self._lines.put(line)

    def send(self, payload) -> dict:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()
        try:
            line = self._lines.get(timeout=_LINE_TIMEOUT_SECONDS)
        except queue.Empty:
            self.kill()
            raise BankFetchError("scraper sidecar timed out")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            stderr = self.proc.stderr.read()
            raise BankFetchError(f"scraper sidecar produced invalid output: {stderr[-2000:]}")

    def kill(self):
        try:
            self.proc.kill()
        except Exception:
            pass


_sessions: dict = {}
_sessions_lock = threading.Lock()


def _reap_stale_sessions():
    now = time.monotonic()
    with _sessions_lock:
        stale = [sid for sid, s in _sessions.items() if now - s["session"].created_at > _SESSION_MAX_AGE_SECONDS]
        for sid in stale:
            _sessions.pop(sid)["session"].kill()


class ScraperClient:
    def __init__(self, settings: Optional[BankSettings] = None):
        self.settings = settings or get_bank_settings()

    def start_login(
        self, credentials: dict, start_date: str, device_trust_data: Optional[dict] = None,
        company_id: Optional[str] = None,
    ) -> dict:
        """Begins a login. Returns {status: 'otp_required', session_id} or
        {status: 'success', ...fetch results}."""
        _reap_stale_sessions()
        session = _SidecarSession(self.settings)
        payload = {
            "companyId": company_id or self.settings.scraper_company_id,
            "credentials": credentials,
            "startDate": start_date,
        }
        if device_trust_data:
            payload["deviceTrustData"] = device_trust_data
        data = session.send(payload)
        return self._handle_response(session, data, credentials, payload["companyId"])

    def submit_otp(self, session_id: str, otp_code: str) -> dict:
        with _sessions_lock:
            entry = _sessions.pop(session_id, None)
        if not entry:
            raise BankAuthError("OTP session has expired — please reconnect")
        data = entry["session"].send(otp_code)
        return self._handle_response(entry["session"], data, entry["credentials"], entry["company_id"])

    def _handle_response(self, session: _SidecarSession, data: dict, credentials: dict, company_id: str) -> dict:
        if data.get("awaitingOtp"):
            session_id = str(uuid.uuid4())
            with _sessions_lock:
                _sessions[session_id] = {"session": session, "credentials": credentials, "company_id": company_id}
            return {"status": "otp_required", "session_id": session_id}

        if not data.get("success"):
            url_note = f" (at {data['lastKnownUrl']})" if data.get("lastKnownUrl") else ""
            raise BankAuthError(
                f"scraper login failed: {data.get('errorType')} {data.get('errorMessage')}{url_note}"
            )

        accounts = []
        transactions_by_account: dict[str, List[NormalizedTxn]] = {}
        for acc in data.get("accounts", []):
            account_ref = acc.get("accountNumber", "")
            accounts.append(BankAccount(account_ref=account_ref, name=account_ref))
            transactions_by_account[account_ref] = [
                _map_transaction(t) for t in acc.get("txns", []) if t.get("status") == "completed"
            ]
        return {
            "status": "success",
            "credentials": credentials,
            "company_id": company_id,
            "accounts": accounts,
            "transactions_by_account": transactions_by_account,
            "device_trust_data": data.get("deviceTrustData"),
        }

    def sync_login(
        self, credentials: dict, start_date: str, device_trust_data: Optional[dict] = None,
        company_id: Optional[str] = None,
    ) -> dict:
        """Non-interactive login for routine syncs. Device trust should make OTP
        unnecessary; if the bank asks for it anyway (trust expired), there's no
        user in the loop to answer, so this fails clearly instead of hanging."""
        result = self.start_login(credentials, start_date, device_trust_data, company_id)
        if result["status"] == "otp_required":
            with _sessions_lock:
                entry = _sessions.pop(result["session_id"], None)
            if entry:
                entry["session"].kill()
            raise BankAuthError(
                "scraper login failed: OTP_REQUIRED bank requires re-verification — reconnect this account"
            )
        return result


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
