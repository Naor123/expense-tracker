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


class SummaryCategory(BaseModel):
    category_id: int
    name: str
    color: str
    amount: float
    percent: float


class SummaryOut(BaseModel):
    month: str
    total: float
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
