from cryptography.fernet import Fernet

from bank.config import get_bank_settings
from bank.errors import BankConfigError


def _fernet() -> Fernet:
    key = get_bank_settings().bank_enc_key
    if not key:
        raise BankConfigError("BANK_ENC_KEY is not set")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
