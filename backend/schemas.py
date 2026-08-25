from datetime import date as _date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict


# ── Auth ──────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[int] = None


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class AccountDeleteRequest(BaseModel):
    password: str


# ── User ──────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    identification_type: Optional[str] = None
    identification_number: Optional[str] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: Optional[str] = None
    identification_type: Optional[str] = "CC"
    identification_number: Optional[str] = None
    created_at: Optional[datetime] = None


# ── Transaction ───────────────────────────────────────────────────────────────

class TransactionBase(BaseModel):
    description: str
    amount: float
    category: str
    type: str
    date: _date


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    type: Optional[str] = None
    date: Optional[_date] = None


class TransactionResponse(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: Optional[datetime] = None


class CategorySummary(BaseModel):
    category: str
    amount: float
    count: int


class TransactionSummary(BaseModel):
    total_income: float
    total_expenses: float
    balance: float
    by_category: List[CategorySummary]


# ── Budget ────────────────────────────────────────────────────────────────────

class BudgetBase(BaseModel):
    category: str
    limit_amount: float
    period: str = "monthly"


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    category: Optional[str] = None
    limit_amount: Optional[float] = None
    period: Optional[str] = None


class BudgetResponse(BudgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: Optional[datetime] = None
    spent_amount: float = 0.0


# ── Saving Goal ───────────────────────────────────────────────────────────────

class SavingGoalBase(BaseModel):
    name: str
    description: Optional[str] = None
    target_amount: float
    deadline: _date


class SavingGoalCreate(SavingGoalBase):
    pass


class SavingGoalUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_amount: Optional[float] = None
    current_amount: Optional[float] = None
    deadline: Optional[_date] = None


class SavingGoalResponse(SavingGoalBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    current_amount: float = 0.0
    created_at: Optional[datetime] = None


class SavingContributionBase(BaseModel):
    amount: float
    note: Optional[str] = None
    date: Optional[_date] = None


class SavingContributionCreate(SavingContributionBase):
    pass


class SavingContributionResponse(SavingContributionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_id: int
    created_at: Optional[datetime] = None


# ── Shared ────────────────────────────────────────────────────────────────────

class SharedGroupMemberBase(BaseModel):
    name: str
    email: Optional[str] = None


class SharedGroupMemberCreate(BaseModel):
    name: str
    email: EmailStr


class SharedGroupMemberUpdate(BaseModel):
    name: str


class SharedGroupMemberResponse(SharedGroupMemberBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    user_id: Optional[int] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class MemberAddResult(BaseModel):
    status: str  # "added" | "invited"
    detail: str
    member: Optional[SharedGroupMemberResponse] = None


class SharedExpenseSplitBase(BaseModel):
    member_id: int
    amount: float


class SharedExpenseSplitCreate(SharedExpenseSplitBase):
    pass


class SharedExpenseSplitResponse(SharedExpenseSplitBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_id: int
    is_settled: bool
    settled_at: Optional[datetime] = None
    settled_by_user_id: Optional[int] = None


class SharedExpenseBase(BaseModel):
    description: str
    amount: float
    paid_by_id: int
    category: Optional[str] = None
    date: _date


class SharedExpenseCreate(SharedExpenseBase):
    splits: Optional[List[SharedExpenseSplitCreate]] = None


class SharedExpenseResponse(SharedExpenseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    created_at: Optional[datetime] = None
    splits: List[SharedExpenseSplitResponse] = []


class SharedGroupBase(BaseModel):
    name: str
    description: Optional[str] = None


class SharedGroupCreate(SharedGroupBase):
    creator_name: Optional[str] = None
    creator_email: Optional[str] = None
    group_type: str = "gastos"


class SharedGroupResponse(SharedGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    group_type: str = "gastos"
    created_at: Optional[datetime] = None
    members: List[SharedGroupMemberResponse] = []
    expenses: List[SharedExpenseResponse] = []


class FundContributionCreate(BaseModel):
    member_id: int
    amount: float
    note: Optional[str] = None
    date: Optional[_date] = None


class FundContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    member_id: int
    amount: float
    note: Optional[str] = None
    date: Optional[_date] = None
    created_at: Optional[datetime] = None


class FundMemberContrib(BaseModel):
    member_id: int
    member_name: str
    total_contributed: float


class FundStatus(BaseModel):
    total_contributed: float
    total_spent: float
    balance: float
    contributions: List[FundContributionResponse]
    per_member: List[FundMemberContrib]


class SettleSelectedSplitsPayload(BaseModel):
    split_ids: List[int]
    creditor_member_id: int


class DebtItem(BaseModel):
    member_id: int
    member_name: str
    amount: float


class Balance(BaseModel):
    member_id: int
    member_name: str
    net_balance: float
    owes_to: List[DebtItem] = []


class SettleResult(BaseModel):
    status: str  # "settled" | "requested"
    detail: str
    amount: float


# ── Notificaciones ────────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    title: str
    body: Optional[str] = None
    group_id: Optional[int] = None
    created_at: Optional[datetime] = None


# ── Recurring ─────────────────────────────────────────────────────────────────

class RecurringServiceBase(BaseModel):
    name: str
    provider: str
    account_reference: str
    category: str
    estimated_amount: float
    billing_day: int


class RecurringServiceCreate(RecurringServiceBase):
    payer_name: Optional[str] = None
    payer_id_type: Optional[str] = None
    payer_id_number: Optional[str] = None
    payer_phone: Optional[str] = None
    payer_email: Optional[str] = None
    payment_identifier: Optional[str] = None


class RecurringServiceUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    account_reference: Optional[str] = None
    category: Optional[str] = None
    estimated_amount: Optional[float] = None
    billing_day: Optional[int] = None
    is_active: Optional[bool] = None
    payer_name: Optional[str] = None
    payer_id_type: Optional[str] = None
    payer_id_number: Optional[str] = None
    payer_phone: Optional[str] = None
    payer_email: Optional[str] = None
    payment_identifier: Optional[str] = None


class RecurringServiceResponse(RecurringServiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    last_fetched_amount: Optional[float] = None
    last_fetched_at: Optional[datetime] = None
    is_active: bool
    created_at: Optional[datetime] = None
    payer_name: Optional[str] = None
    payer_id_type: Optional[str] = None
    payer_id_number: Optional[str] = None
    payer_phone: Optional[str] = None
    payer_email: Optional[str] = None
    payment_identifier: Optional[str] = None


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    amount: float
    due_date: _date
    fetched_at: datetime
    is_paid: bool
    paid_at: Optional[datetime] = None
    qr_data: Optional[str] = None


class InvoiceResult(BaseModel):
    amount: float
    due_date: _date
    reference: str
    qr_base64: str
    service_name: str
    payment_url: str = ""
    is_demo: bool = False
    is_up_to_date: bool = False
    portal_blocked: bool = False
    blocked_reason: str = ""


class PatternResult(BaseModel):
    service_id: Optional[int] = None
    service_name: str
    detected_day: int
    confidence: float
    next_predicted_date: _date
    occurrences: int = 0
    first_seen: Optional[_date] = None
    last_seen: Optional[_date] = None


class TrendResult(BaseModel):
    category: str
    avg_last_3m: float
    avg_prev_3m: float
    pct_change: float
    trend: str  # "sube" | "baja" | "estable"


# ── Monthly summary ───────────────────────────────────────────────────────────

class MonthlyPoint(BaseModel):
    month: str
    label: str
    income: float
    expenses: float


# ── Invoice lookup (standalone) ───────────────────────────────────────────────

class InvoiceLookupRequest(BaseModel):
    provider: str
    account_reference: str
    service_name: Optional[str] = None


class InvoiceLookupResult(BaseModel):
    amount: float
    due_date: str
    reference: str
    qr_base64: str
    service_name: str
    provider: str
    payment_url: str = ""
    is_demo: bool = False
    is_up_to_date: bool = False


class ProviderInfo(BaseModel):
    id: str
    name: str
    category: str
    logo_hint: str
    real_scraper: bool = False


# ── PSE Payment ───────────────────────────────────────────────────────────────

class PSEBank(BaseModel):
    code: str
    name: str


class PSEInitResponse(BaseModel):
    session_id: str
    banks: List[PSEBank]
    amount: float
    due_date: str
    reference: str
    is_up_to_date: bool = False


# ── PSE Payment (Movistar): sondeo en segundo plano ───────────────────────────
# El flujo real (navegar el portal, reintentar si reCAPTCHA lo rechaza) puede
# tardar más de un minuto; en vez de sostener una sola conexión HTTP todo ese
# tiempo (frágil sobre túneles/proxies), el backend arranca el trabajo y el
# frontend sondea el estado — mismo patrón que EmcaliCaptchaResponse.

class MovistarPollStart(BaseModel):
    estado: str        # siempre "consultando" al arrancar
    poll_id: str


class MovistarPollRequest(BaseModel):
    poll_id: str


class MovistarInitStatus(BaseModel):
    estado: str        # "consultando" | "listo"
    session_id: Optional[str] = None
    banks: List[PSEBank] = []
    amount: Optional[float] = None
    due_date: Optional[str] = None
    reference: Optional[str] = None
    is_up_to_date: Optional[bool] = None


class MovistarPayStatus(BaseModel):
    estado: str        # "consultando" | "listo"
    pse_url: Optional[str] = None


class PSEPayRequest(BaseModel):
    session_id: str
    bank_code: str
    guardar_datos: bool = False


class PSEPayResponse(BaseModel):
    pse_url: str


# ── EMCALI: reCAPTCHA resuelto por el usuario ─────────────────────────────────

class EmcaliCaptchaResponse(BaseModel):
    """
    estado:
      "desafio"     → hay que mostrar `imagen` y reenviar los clics
      "consultando" → captcha resuelto, esperando al portal
      "listo"       → `resultado` trae la factura
    """
    estado: str
    session_id: Optional[str] = None
    imagen: Optional[str] = None      # PNG en base64 del desafío
    ancho: Optional[int] = None
    alto: Optional[int] = None
    resultado: Optional[InvoiceResult] = None


class EmcaliClickRequest(BaseModel):
    session_id: str
    x: float                          # proporción 0..1 sobre el ancho del recorte
    y: float                          # proporción 0..1 sobre el alto


class EmcaliSessionRequest(BaseModel):
    session_id: str
