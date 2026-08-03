import base64
import hashlib
import uuid
from datetime import date
from typing import List, Optional

import httpx

from bank.config import BankSettings, get_bank_settings
from bank.errors import BankAuthError, BankConfigError, BankFetchError
from bank.types import BankAccount, NormalizedTxn

# BOI's NextGenPSD2 profile supports only the OAuth SCA Approach (the plain
# "scaRedirect" link is commented out of the spec's _linksConsents schema) —
# so authorization is a standard OAuth2 authorization-code flow: the
# consent's "scaOAuth" link points at an OAuth 2.0 Authorization Server
# Metadata document (RFC 8414), not directly at a bank login page.


class Psd2Client:
    def __init__(self, settings: Optional[BankSettings] = None):
        self.settings = settings or get_bank_settings()

    def _cert(self):
        if self.settings.psd2_client_cert and self.settings.psd2_client_key:
            return (self.settings.psd2_client_cert, self.settings.psd2_client_key)
        return None

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.psd2_base_url,
            cert=self._cert(),
            verify=self.settings.psd2_ca_bundle or True,
            timeout=30.0,
        )

    def _signed_headers(self, body: bytes = b"") -> dict:
        headers = {"X-Request-ID": str(uuid.uuid4())}
        if self.settings.psd2_psu_id:
            headers["PSU-ID"] = self.settings.psd2_psu_id
        if self.settings.psd2_signing_key:
            digest = base64.b64encode(hashlib.sha256(body).digest()).decode()
            headers["Digest"] = f"SHA-256={digest}"
            # A real QSEALC signature over `headers["Digest"]` would be computed
            # here with self.settings.psd2_signing_key; omitted so the client
            # also works unsigned against the local mock server.
        return headers

    def create_consent(self) -> dict:
        """POST /v1/consents (YAML:2171) — returns {consentId, sca_oauth_url}."""
        body = {
            "access": {"transactions": []},
            "recurringIndicator": True,
            "validUntil": "9999-12-31",
            "frequencyPerDay": 100,
            "combinedServiceIndicator": False,
        }
        headers = self._signed_headers()
        headers["TPP-Redirect-Preferred"] = "true"
        headers["TPP-Redirect-URI"] = self.settings.psd2_redirect_uri
        headers["TPP-Nok-Redirect-URI"] = self.settings.psd2_redirect_uri
        with self._client() as client:
            resp = client.post("/v1/consents", json=body, headers=headers)
        if resp.status_code != 201:
            raise BankAuthError(f"createConsent failed: {resp.status_code} {resp.text}")
        data = resp.json()
        links = data.get("_links", {})
        sca_oauth = links.get("scaOAuth", {}).get("href") if isinstance(links.get("scaOAuth"), dict) else links.get("scaOAuth")
        return {"consent_id": data["consentId"], "sca_oauth_url": sca_oauth, "status": data.get("consentStatus")}

    def get_oauth_metadata(self, sca_oauth_url: str) -> dict:
        """GET the OAuth 2.0 Authorization Server Metadata document (RFC 8414)."""
        with httpx.Client(cert=self._cert(), verify=self.settings.psd2_ca_bundle or True, timeout=30.0) as client:
            resp = client.get(sca_oauth_url)
        if resp.status_code != 200:
            raise BankAuthError(f"OAuth metadata fetch failed: {resp.status_code}")
        return resp.json()

    def build_authorization_url(self, oauth_metadata: dict, consent_id: str, client_id: str, state: str) -> str:
        auth_endpoint = oauth_metadata["authorization_endpoint"]
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": self.settings.psd2_redirect_uri,
            "scope": f"AIS:{consent_id}",
            "state": state,
        }
        query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
        return f"{auth_endpoint}?{query}"

    def exchange_code(self, oauth_metadata: dict, code: str, client_id: str, client_secret: Optional[str]) -> dict:
        token_endpoint = oauth_metadata["token_endpoint"]
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.psd2_redirect_uri,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret
        with httpx.Client(cert=self._cert(), verify=self.settings.psd2_ca_bundle or True, timeout=30.0) as client:
            resp = client.post(token_endpoint, data=data)
        if resp.status_code != 200:
            raise BankAuthError(f"token exchange failed: {resp.status_code} {resp.text}")
        return resp.json()

    def get_consent_status(self, consent_id: str, access_token: str) -> str:
        """GET /v1/consents/{consentId}/status (YAML:2456)."""
        headers = self._signed_headers()
        headers["Authorization"] = f"Bearer {access_token}"
        with self._client() as client:
            resp = client.get(f"/v1/consents/{consent_id}/status", headers=headers)
        if resp.status_code != 200:
            raise BankFetchError(f"getConsentStatus failed: {resp.status_code} {resp.text}")
        return resp.json()["consentStatus"]

    def revoke_consent(self, consent_id: str, access_token: str) -> None:
        """DELETE /v1/consents/{consentId} (YAML:2379)."""
        headers = self._signed_headers()
        headers["Authorization"] = f"Bearer {access_token}"
        with self._client() as client:
            client.delete(f"/v1/consents/{consent_id}", headers=headers)

    def list_accounts(self, access_token: str) -> List[BankAccount]:
        """GET /v1/accounts (YAML:1360)."""
        headers = self._signed_headers()
        headers["Authorization"] = f"Bearer {access_token}"
        with self._client() as client:
            resp = client.get("/v1/accounts", headers=headers)
        if resp.status_code != 200:
            raise BankFetchError(f"getAccountList failed: {resp.status_code} {resp.text}")
        accounts = resp.json().get("accounts", [])
        return [
            BankAccount(
                account_ref=a.get("resourceId") or a.get("iban", ""),
                name=a.get("name") or a.get("product"),
                currency=a.get("currency"),
            )
            for a in accounts
        ]

    def fetch_transactions(
        self, account_ref: str, consent_id: str, access_token: str, date_from: str, date_to: str
    ) -> List[NormalizedTxn]:
        """GET /v1/accounts/{account-id}/transactions (YAML:1640)."""
        headers = self._signed_headers()
        headers["Authorization"] = f"Bearer {access_token}"
        headers["Consent-ID"] = consent_id
        params = {"dateFrom": date_from, "dateTo": date_to, "bookingStatus": "booked"}
        results: List[NormalizedTxn] = []
        url = f"/v1/accounts/{account_ref}/transactions"
        with self._client() as client:
            while url:
                resp = client.get(url, headers=headers, params=params if url.startswith("/v1/") else None)
                if resp.status_code != 200:
                    raise BankFetchError(f"getTransactionList failed: {resp.status_code} {resp.text}")
                payload = resp.json()
                booked = payload.get("transactions", {}).get("booked", [])
                results.extend(_map_transaction(t) for t in booked)
                next_link = payload.get("transactions", {}).get("_links", {}).get("next")
                url = next_link.get("href") if isinstance(next_link, dict) else next_link
                params = None
        return results


def _map_transaction(t: dict) -> NormalizedTxn:
    amount_obj = t.get("transactionAmount", {})
    creditor = t.get("creditorName")
    debtor = t.get("debtorName")
    return NormalizedTxn(
        external_id=t.get("transactionId") or t.get("entryReference") or str(uuid.uuid4()),
        booking_date=t.get("bookingDate") or date.today().isoformat(),
        value_date=t.get("valueDate"),
        amount=float(amount_obj.get("amount", 0)),
        currency=amount_obj.get("currency", "ILS"),
        counterparty=creditor or debtor,
        description=t.get("remittanceInformationUnstructured") or t.get("additionalInformation"),
        raw=t,
    )
