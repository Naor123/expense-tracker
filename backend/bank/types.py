from typing import Optional

from pydantic import BaseModel


class BankAccount(BaseModel):
    account_ref: str
    name: Optional[str] = None
    currency: Optional[str] = None


class NormalizedTxn(BaseModel):
    external_id: str
    booking_date: str
    value_date: Optional[str] = None
    amount: float
    currency: str = "ILS"
    counterparty: Optional[str] = None
    description: Optional[str] = None
    raw: dict
