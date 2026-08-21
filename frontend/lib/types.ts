// auth
export interface User {
  id: number
  email: string
  full_name: string
  phone?: string
  identification_type?: string
  identification_number?: string
  created_at: string
}

export interface UserProfileUpdate {
  full_name?: string
  phone?: string
  identification_type?: string
  identification_number?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
}

// transactions
export type TransactionType = "ingreso" | "gasto"

export interface Transaction {
  id: number
  description: string
  amount: number
  category: string
  type: TransactionType
  date: string
  user_id: number
  created_at: string
}

export interface TransactionCreate {
  description: string
  amount: number
  category: string
  type: TransactionType
  date: string
}

export interface TransactionUpdate {
  description?: string
  amount?: number
  category?: string
  type?: TransactionType
  date?: string
}

export interface CategorySummary {
  category: string
  amount: number
  count: number
}

export interface TransactionSummary {
  total_income: number
  total_expenses: number
  balance: number
  by_category: CategorySummary[]
}

// budgets
export interface Budget {
  id: number
  category: string
  limit_amount: number
  period: string
  spent_amount: number
  user_id: number
  created_at: string
}

export interface BudgetCreate {
  category: string
  limit_amount: number
  period?: string
}

export interface BudgetUpdate {
  category?: string
  limit_amount?: number
  period?: string
}

// goals
export interface SavingGoal {
  id: number
  name: string
  description?: string
  target_amount: number
  current_amount: number
  deadline: string
  user_id: number
  created_at: string
}

export interface GoalCreate {
  name: string
  description?: string
  target_amount: number
  deadline: string
}

export interface GoalUpdate {
  name?: string
  description?: string
  target_amount?: number
  deadline?: string
}

export interface Contribution {
  id: number
  goal_id: number
  amount: number
  note?: string
  date: string
  created_at: string
}

export interface ContributionCreate {
  amount: number
  note?: string
  date?: string
}

// shared
export interface SharedGroup {
  id: number
  name: string
  description?: string
  creator_id: number
  group_type: "gastos" | "fondo"
  created_at: string
}

export interface SharedGroupMember {
  id: number
  group_id: number
  user_id?: number
  is_active: boolean
  name: string
  email?: string
  created_at: string
}

export interface SharedExpenseSplit {
  id: number
  expense_id: number
  member_id: number
  amount: number
  is_settled: boolean
  settled_at?: string
}

export interface SharedExpense {
  id: number
  group_id: number
  description: string
  amount: number
  paid_by_id: number
  category?: string
  date: string
  created_at: string
  splits: SharedExpenseSplit[]
}

export interface GroupDetail {
  id: number
  name: string
  description?: string
  creator_id: number
  group_type: "gastos" | "fondo"
  created_at: string
  members: SharedGroupMember[]
  expenses: SharedExpense[]
}

export interface GroupFundContribution {
  id: number
  group_id: number
  member_id: number
  amount: number
  note?: string
  date?: string
  created_at: string
}

export interface GroupFundContributionCreate {
  member_id: number
  amount: number
  note?: string
  date?: string
}

export interface FundMemberContrib {
  member_id: number
  member_name: string
  total_contributed: number
}

export interface FundStatus {
  total_contributed: number
  total_spent: number
  balance: number
  contributions: GroupFundContribution[]
  per_member: FundMemberContrib[]
}

export interface DebtItem {
  member_id: number
  member_name: string
  amount: number
}

export interface MemberBalance {
  member_id: number
  member_name: string
  net_balance: number
  owes_to: DebtItem[]
}

export interface GroupCreate {
  name: string
  description?: string
  group_type?: "gastos" | "fondo"
}

export interface MemberCreate {
  name: string
  email?: string
}

export interface ExpenseCreate {
  description: string
  amount: number
  paid_by_id: number
  category?: string
  date: string
  splits?: { member_id: number; amount: number }[]
}

// recurring
export interface RecurringService {
  id: number
  name: string
  provider: string
  account_reference: string
  category: string
  estimated_amount: number
  billing_day: number
  last_fetched_amount?: number
  last_fetched_at?: string
  is_active: boolean
  user_id: number
  created_at: string
  payer_name?: string
  payer_id_type?: string
  payer_id_number?: string
  payer_phone?: string
  payer_email?: string
  payment_identifier?: string
}

export interface RecurringCreate {
  name: string
  provider: string
  account_reference: string
  category: string
  estimated_amount: number
  billing_day: number
  payer_name?: string
  payer_id_type?: string
  payer_id_number?: string
  payer_phone?: string
  payer_email?: string
}

export interface RecurringUpdate {
  name?: string
  provider?: string
  account_reference?: string
  category?: string
  estimated_amount?: number
  billing_day?: number
}

export interface InvoiceResult {
  amount: number
  due_date: string
  reference: string
  qr_base64: string
  service_name: string
  payment_url: string
  is_demo: boolean
  is_up_to_date: boolean
  portal_blocked: boolean
  blocked_reason?: string
}

export interface PatternResult {
  service_id?: number
  service_name: string
  detected_day: number
  confidence: number
  next_predicted_date: string
  occurrences: number
  first_seen?: string
  last_seen?: string
}

// ml
export interface MLSuggestion {
  category: string | null
  confidence: number
  alternatives: { category: string; confidence: number }[]
}

export interface MLMetrics {
  accuracy: number | null
  f1_weighted: number | null
  n_samples: number
  n_categories: number
  categories: string[]
  top_features: { word: string; importance: number }[]
  cv_folds: number
  message?: string
}

export interface AnomalyScore {
  transaction_id: number
  anomaly_score: number
  is_anomaly: boolean
}

// PSE payment
export interface PSEBank {
  code: string
  name: string
}

export interface PSEInitResponse {
  session_id: string
  banks: PSEBank[]
  amount: number
  due_date: string
  reference: string
  is_up_to_date: boolean
}

export interface PSEPayRequest {
  session_id: string
  bank_code: string
}

export interface PSEPayResponse {
  pse_url: string
}

// EMCALI: reCAPTCHA resuelto por el usuario
export type EmcaliEstado = "desafio" | "consultando" | "listo"

export interface EmcaliCaptchaResponse {
  estado: EmcaliEstado
  session_id?: string
  imagen?: string        // PNG en base64 del desafío
  ancho?: number
  alto?: number
  resultado?: InvoiceResult
}

// trends
export interface TrendResult {
  category: string
  avg_last_3m: number
  avg_prev_3m: number
  pct_change: number
  trend: "sube" | "baja" | "estable"
}

// monthly
export interface MonthlyPoint {
  month: string
  label: string
  income: number
  expenses: number
}

// invoices
export interface ProviderInfo {
  id: string
  name: string
  category: string
  logo_hint: string
  real_scraper: boolean
}

export interface InvoiceLookupRequest {
  provider: string
  account_reference: string
  service_name?: string
}

export interface InvoiceLookupResult {
  amount: number
  due_date: string
  reference: string
  qr_base64: string
  service_name: string
  provider: string
  payment_url: string
  is_demo: boolean
  is_up_to_date: boolean
}
