from typing import Optional

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str
    color: str


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class CategoryOut(BaseModel):
    id: int
    name: str
    color: str


class ExpenseUpdate(BaseModel):
    category_id: int
    remember: bool = True


class ExpenseOut(BaseModel):
    id: int
    amount: float
    category_id: int
    category_name: str
    category_color: str
    date: str
    note: Optional[str] = None
    is_rent: bool = False
    bank_txn_id: Optional[int] = None
    settlement: Optional[str] = None


class SummaryCategory(BaseModel):
    category_id: int
    name: str
    color: str
    amount: float
    percent: float


class SummaryOut(BaseModel):
    month: str
    total: float
    pending_settlement: float
    categories: list[SummaryCategory]


class InsightsEmailOut(BaseModel):
    sent: bool
    recipient: str


class SalaryUpdate(BaseModel):
    amount: float = Field(gt=0)


class SalaryOut(BaseModel):
    month: str
    amount: Optional[float] = None
    source: Optional[str] = None


class BankConnectCreate(BaseModel):
    provider: str  # 'psd2' | 'scraper'
    label: str
    # scraper only:
    company_id: Optional[str] = None  # 'hapoalim' | 'max'
    user_code: Optional[str] = None
    password: Optional[str] = None


class BankConnectionOut(BaseModel):
    id: int
    provider: str
    company_id: Optional[str] = None
    label: str
    account_ref: Optional[str] = None
    status: str
    consent_valid_until: Optional[str] = None
    last_synced_at: Optional[str] = None
    last_error: Optional[str] = None
    sca_redirect_url: Optional[str] = None  # only set right after a psd2 /bank/connect


class BankConnectOtpSubmit(BaseModel):
    session_id: str
    otp_code: str
    label: str


class BankReverifyOtpSubmit(BaseModel):
    session_id: str
    otp_code: str


class BankSyncOut(BaseModel):
    fetched: int
    inserted: int
    skipped: int
    imported: int = 0
    ignored: int = 0
    salary: int = 0


class BankBackfillOut(BaseModel):
    imported: int
    ignored: int
    salary: int


class BankTransactionOut(BaseModel):
    id: int
    connection_id: int
    external_id: str
    booking_date: str
    value_date: Optional[str] = None
    amount: float
    currency: str
    counterparty: Optional[str] = None
    description: Optional[str] = None
    status: str
    kind: str
    settlement: str
    suggested_category_id: Optional[int] = None
    suggested_category_name: Optional[str] = None
    current_category_name: Optional[str] = None
    expense_id: Optional[int] = None
    ignore_reason: Optional[str] = None
    connection_company_id: Optional[str] = None
    connection_label: Optional[str] = None


class CategoryRuleCreate(BaseModel):
    pattern: str
    category_id: int


class CategoryRuleOut(BaseModel):
    id: int
    pattern: str
    category_id: int
    category_name: str
