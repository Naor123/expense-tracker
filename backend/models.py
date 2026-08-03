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


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    category_id: int
    date: str
    note: Optional[str] = None


class ExpenseOut(BaseModel):
    id: int
    amount: float
    category_id: int
    category_name: str
    category_color: str
    date: str
    note: Optional[str] = None
    recurring_id: Optional[int] = None
    bank_txn_id: Optional[int] = None


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


class RecurringBillCreate(BaseModel):
    name: str
    amount: float = Field(gt=0)
    category_id: int
    interval_months: int = 1
    month_parity: Optional[str] = None
    start_month: Optional[str] = None


class RecurringBillUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    category_id: Optional[int] = None
    active: Optional[bool] = None
    apply_amount_to: Optional[str] = None  # 'current' or 'all' — only used when amount changes


class RecurringBillOut(BaseModel):
    id: int
    name: str
    amount: float
    category_id: int
    category_name: str
    category_color: str
    interval_months: int
    month_parity: Optional[str] = None
    start_month: str
    active: bool


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
    expense_id: Optional[int] = None
    possible_duplicate: bool = False


class BankTransactionApprove(BaseModel):
    category_id: int
    note: Optional[str] = None
    save_rule: bool = False
    rule_pattern: Optional[str] = None


class BankTransactionMarkSalary(BaseModel):
    save_rule: bool = False


class BankTransactionsBulkApprove(BaseModel):
    ids: list[int]


class CategoryRuleCreate(BaseModel):
    pattern: str
    category_id: int


class CategoryRuleOut(BaseModel):
    id: int
    pattern: str
    category_id: int
    category_name: str
