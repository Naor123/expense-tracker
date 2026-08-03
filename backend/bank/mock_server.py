"""
Standalone mock ASPSP for local testing of bank/psd2.py against the shape of
the BOI NextGenPSD2 v1.7 spec, without real bank credentials.

Run with: uvicorn bank.mock_server:app --port 8010
Then point PSD2_BASE_URL=http://localhost:8010 (and PSD2_REDIRECT_URI at the
expense-tracker backend's /bank/callback).

Replays the spec's own examples (accountListExample1, YAML:13107) and
auto-approves SCA immediately instead of showing a login page, since this
exists to exercise the code path, not to simulate real authentication.
"""
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

app = FastAPI(title="Mock BOI PSD2 ASPSP")

_CONSENTS: dict[str, dict] = {}
_AUTH_CODES: dict[str, str] = {}
_ACCESS_TOKENS: dict[str, str] = {}

_ACCOUNTS = [
    {
        "resourceId": "3dc3d5b3-7023-4848-9853-f5400a64e80f",
        "iban": "IL120108000000099999999",
        "currency": "ILS",
        "product": "Checking",
        "cashAccountType": "CACC",
        "name": "Main Account",
    }
]

_TRANSACTIONS = [
    {
        "transactionId": "tx-1001",
        "bookingDate": "2026-07-05",
        "valueDate": "2026-07-05",
        "transactionAmount": {"amount": "-160.00", "currency": "ILS"},
        "creditorName": "Bezeq Internet",
        "remittanceInformationUnstructured": "ISP monthly bill",
    },
    {
        "transactionId": "tx-1002",
        "bookingDate": "2026-07-08",
        "valueDate": "2026-07-08",
        "transactionAmount": {"amount": "-89.90", "currency": "ILS"},
        "creditorName": "Super-Pharm",
        "remittanceInformationUnstructured": "Card purchase",
    },
    {
        "transactionId": "tx-1003",
        "bookingDate": "2026-07-10",
        "valueDate": "2026-07-10",
        "transactionAmount": {"amount": "12000.00", "currency": "ILS"},
        "debtorName": "Employer Ltd",
        "remittanceInformationUnstructured": "Salary",
    },
]


@app.post("/v1/consents", status_code=201)
async def create_consent(request: Request):
    body = await request.json()
    consent_id = str(uuid.uuid4())
    _CONSENTS[consent_id] = {"status": "received", "access": body.get("access", {})}
    base = str(request.base_url).rstrip("/")
    return {
        "consentStatus": "received",
        "consentId": consent_id,
        "_links": {
            "scaOAuth": {"href": f"{base}/.well-known/oauth-authorization-server"},
            "self": {"href": f"{base}/v1/consents/{consent_id}"},
            "status": {"href": f"{base}/v1/consents/{consent_id}/status"},
        },
    }


@app.get("/v1/consents/{consent_id}/status")
async def consent_status(consent_id: str):
    consent = _CONSENTS.get(consent_id, {})
    return {"consentStatus": consent.get("status", "received")}


@app.get("/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
    }


@app.get("/oauth/authorize")
async def authorize(scope: str, redirect_uri: str, state: str):
    consent_id = scope.split(":", 1)[-1] if ":" in scope else scope
    code = str(uuid.uuid4())
    _AUTH_CODES[code] = consent_id
    if consent_id in _CONSENTS:
        _CONSENTS[consent_id]["status"] = "valid"
    return RedirectResponse(url=f"{redirect_uri}?code={code}&state={state}")


@app.post("/oauth/token")
async def token(request: Request):
    form = await request.form()
    code = form.get("code")
    consent_id = _AUTH_CODES.get(code)
    access_token = str(uuid.uuid4())
    _ACCESS_TOKENS[access_token] = consent_id
    return {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600}


@app.get("/v1/accounts")
async def accounts():
    return {
        "accounts": [
            {**a, "_links": {"transactions": {"href": f"/v1/accounts/{a['resourceId']}/transactions"}}}
            for a in _ACCOUNTS
        ]
    }


@app.get("/v1/accounts/{account_id}/transactions")
async def transactions(account_id: str, dateFrom: str = "", dateTo: str = "", bookingStatus: str = "booked"):
    return {
        "transactions": {
            "booked": _TRANSACTIONS,
            "_links": {},
        },
        "account": {"resourceId": account_id},
    }
