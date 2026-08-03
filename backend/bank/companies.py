# Scraper companies this app knows how to connect to, and the credential
# field name each one's israeli-bank-scrapers class expects (checked against
# the vendored fork's source — Hapoalim uses `userCode`, Max uses `username`).
SCRAPER_COMPANIES = {
    "hapoalim": {"credential_field": "userCode", "kind": "bank"},
    "max": {"credential_field": "username", "kind": "credit_card"},
}
