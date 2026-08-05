from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class BankSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bank_enc_key: Optional[str] = None

    psd2_base_url: str = "http://localhost:8010"
    psd2_client_id: str = "expense-tracker"
    psd2_client_secret: Optional[str] = None
    psd2_client_cert: Optional[str] = None
    psd2_client_key: Optional[str] = None
    psd2_ca_bundle: Optional[str] = None
    psd2_signing_key: Optional[str] = None
    psd2_signing_cert: Optional[str] = None
    psd2_psu_id: Optional[str] = None
    psd2_redirect_uri: str = "http://localhost:8000/bank/callback"

    scraper_company_id: str = "hapoalim"
    scraper_node_path: str = "node"


def get_bank_settings() -> BankSettings:
    return BankSettings()
