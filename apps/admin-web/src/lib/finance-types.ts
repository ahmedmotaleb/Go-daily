/** Types for the finance API (Tasks 14-19). Money is always a decimal string. */

export type RecordStatus = "SUBMITTED" | "APPROVED" | "REJECTED" | "VOIDED";
export type RecordSource = "ADMIN" | "DRIVER_APP" | "SYSTEM";
export type PaymentMethod = "CASH" | "CARD" | "BANK_TRANSFER" | "WALLET" | "PLATFORM" | "OTHER";
export type PaidBy = "COMPANY" | "DRIVER";
export type ReceivedBy = "DRIVER" | "COMPANY";
export type QuantityUnit = "LITER" | "CUBIC_METER" | "KG" | "UNIT";
export type FuelCategory = "FUEL" | "CONSUMABLE";
export type ExpenseGroup = "OPERATING" | "MAINTENANCE" | "FINES" | "OTHER";
export type RevenueKind =
  "FIXED_ROUTE_COLLECTION" | "CONTRACT_SERVICE" | "PRIVATE_TRIP" | "RIDE_HAILING" | "OTHER";
export type LedgerEntryType =
  | "EARNING"
  | "BONUS"
  | "REIMBURSEMENT"
  | "CASH_HANDOVER"
  | "ADVANCE"
  | "DEDUCTION"
  | "PAYMENT"
  | "CASH_COLLECTED"
  | "ADJUSTMENT";
export type SettlementStatus = "DRAFT" | "REVIEWED" | "FINALIZED" | "PAID" | "VOIDED";

export type Ref = { id: string; name: string };
export type UserRef = { id: string; full_name: string };

export type Reviewable = {
  id: string;
  status: RecordStatus;
  source: RecordSource;
  notes: string | null;
  created_by: UserRef | null;
  created_at: string;
  updated_at: string;
  reviewed_by: UserRef | null;
  reviewed_at: string | null;
  review_note: string | null;
  voided_by: UserRef | null;
  voided_at: string | null;
  void_reason: string | null;
  corrects_id: string | null;
  corrected_by_id: string | null;
};

export type FuelType = {
  id: string;
  code: string;
  name_ar: string;
  category: FuelCategory;
  default_unit: QuantityUnit;
  is_active: boolean;
  sort_order: number;
};

export type FuelTx = Reviewable & {
  vehicle: Ref;
  driver: Ref | null;
  shift_id: string | null;
  fuel_type: FuelType;
  quantity: string;
  unit: QuantityUnit;
  unit_price: string | null;
  effective_unit_price: string;
  total_amount: string;
  occurred_at: string;
  odometer_km: number | null;
  vendor: string | null;
  station: Ref | null;
  payment_method: PaymentMethod;
  paid_by: PaidBy;
  receipt_attachment_id: string | null;
  latitude: number | null;
  longitude: number | null;
  location_accuracy_m: number | null;
  /** Phone clock when the driver saved it (driver-app entries). */
  device_recorded_at?: string | null;
};

export type FuelSummary = {
  by_type: { fuel_type: FuelType; count: number; quantity: string; total_amount: string }[];
  fuel_amount: string;
  consumables_amount: string;
  pending_count: number;
};

export type ExpenseCategory = {
  id: string;
  code: string;
  name_ar: string;
  pnl_group: ExpenseGroup;
  is_active: boolean;
  sort_order: number;
};

export type Expense = Reviewable & {
  vehicle: Ref;
  driver: Ref | null;
  shift_id: string | null;
  session_id: string | null;
  category: ExpenseCategory;
  amount: string;
  occurred_at: string;
  vendor: string | null;
  station: Ref | null;
  payment_method: PaymentMethod;
  paid_by: PaidBy;
  receipt_attachment_id: string | null;
};

export type ExpenseSummary = {
  by_category: { category: ExpenseCategory; count: number; amount: string }[];
  total_amount: string;
  pending_count: number;
};

export type Receipt = {
  id: string;
  amount: string;
  received_at: string;
  method: PaymentMethod;
  received_by: ReceivedBy;
  reference: string | null;
  notes: string | null;
  created_by: UserRef | null;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
};

export type RevenueEntry = Reviewable & {
  kind: RevenueKind;
  vehicle: Ref;
  driver: Ref | null;
  shift_id: string | null;
  session_id: string | null;
  operation_type: Ref | null;
  occurred_on: string;
  period_start: string | null;
  period_end: string | null;
  amount: string;
  fees_withheld: string;
  net_amount: string;
  received_amount: string;
  received_cash: string;
  received_electronic: string;
  outstanding_amount: string;
  loops_count: number | null;
  customer_name: string | null;
  reference: string | null;
  statement_id: string | null;
  receipts: Receipt[];
};

export type RevenueSummary = {
  by_kind: Partial<Record<RevenueKind, string>>;
  gross_amount: string;
  fees_withheld: string;
  received_cash: string;
  received_electronic: string;
  outstanding_amount: string;
  pending_count: number;
};

export type Platform = { id: string; name: string; is_active: boolean; notes: string | null };

export type Statement = Reviewable & {
  platform: Ref;
  driver: Ref;
  vehicle: Ref;
  period_start: string;
  period_end: string;
  trips_count: number | null;
  gross_earnings: string;
  platform_fees: string;
  tips: string;
  adjustments: string;
  income: string;
  net_earnings: string;
  cash_collected: string;
  platform_payout: string;
  payout_recipient: ReceivedBy;
  statement_reference: string | null;
  attachment_id: string | null;
  revenue_entry_id: string | null;
};

export type ReconciliationRow = {
  statement: Statement | null;
  driver: Ref;
  vehicle: Ref;
  period_start: string;
  period_end: string;
  shifts_count: number;
  ride_hailing_minutes: number;
  odometer_km: number | null;
  gps_km: number | null;
  net_per_hour: string | null;
  net_per_km: string | null;
  flags: { code: string; message: string }[];
};

export type Reconciliation = { rows: ReconciliationRow[]; uncovered: ReconciliationRow[] };

export type LedgerEntry = {
  id: string;
  driver_id: string;
  entry_type: LedgerEntryType;
  amount: string;
  occurred_on: string;
  description: string;
  reason: string | null;
  source_type: "MANUAL" | "SETTLEMENT" | "EXPENSE" | "FUEL" | "REVENUE_RECEIPT";
  source_id: string | null;
  settlement_id: string | null;
  vehicle_id: string | null;
  period_start: string | null;
  period_end: string | null;
  created_by: UserRef | null;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
};

export type DriverStatement = {
  driver: Ref;
  date_from: string;
  date_to: string;
  opening_balance: string;
  earned: string;
  bonuses: string;
  reimbursements: string;
  cash_collected: string;
  cash_handed_over: string;
  advances: string;
  deductions: string;
  paid: string;
  adjustments: string;
  closing_balance: string;
  entries: LedgerEntry[];
};

export type SettlementLine = {
  plan_id: string;
  method: string;
  label: string;
  period_start: string;
  period_end: string;
  basis: string;
  amount: string;
};

export type Settlement = {
  id: string;
  driver: Ref;
  period_start: string;
  period_end: string;
  status: SettlementStatus;
  earnings_amount: string;
  details: {
    lines: SettlementLine[];
    warnings: string[];
    days_worked: number;
    eligible_revenue: string;
    computed_at: string;
    computed_total?: string;
    adjustments?: { amount: string; reason: string; by: string; at: string }[];
    account?: { opening_balance: string; by_type: Record<string, string>; period_entries: string };
    expected_balance?: string;
  };
  opening_balance: string | null;
  closing_balance: string | null;
  notes: string | null;
  created_at: string;
  finalized_at: string | null;
  finalized_by: UserRef | null;
  voided_at: string | null;
  void_reason: string | null;
  reviewed_at?: string | null;
  reviewed_by?: UserRef | null;
  paid_at?: string | null;
  paid_by?: UserRef | null;
  paid_on?: string | null;
  paid_amount?: string | null;
  payment_method?: PaymentMethod | null;
  payment_reference?: string | null;
};

export type PnlWarning = { code: string; message: string; count: number | null };

export type VehiclePnl = {
  vehicle: Ref;
  date_from: string;
  date_to: string;
  gross_revenue: string;
  platform_fees: string;
  fuel_by_type: Record<string, string>;
  fuel_cost: string;
  consumables_cost: string;
  maintenance_cost: string;
  expenses_by_group: Record<string, string>;
  other_expenses: string;
  direct_operating_cost: string;
  driver_cost: string;
  net_operating_profit: string;
  shifts_count: number;
  odometer_km: number;
  gps_km: number;
  cost_per_km: string | null;
  revenue_per_km: string | null;
  profit_per_shift: string | null;
  profit_per_km?: string | null;
  loops_count?: number;
  profit_per_loop?: string | null;
  oil_and_service_cost?: string;
  by_route?: {
    route: Ref | null;
    revenue: string;
    allocated_cost: string;
    profit: string;
    session_minutes: number;
  }[];
  by_operation_type: {
    operation_type: Ref | null;
    revenue: string;
    allocated_cost: string;
    profit: string;
    session_minutes: number;
  }[];
  warnings: PnlWarning[];
};

export type FleetPnl = {
  date_from: string;
  date_to: string;
  vehicles: VehiclePnl[];
  totals: Record<string, string>;
};

/** One fuel plausibility check (U15). */
export type PlausibilityCheck = {
  code:
    | "ASSIGNMENT"
    | "SHIFT_TIME"
    | "ODOMETER"
    | "LOCATION"
    | "QUANTITY"
    | "RAPID_REPEAT"
    | "DUPLICATE";
  result: "PASS" | "FAIL" | "NOT_CHECKABLE";
  observed: unknown;
  threshold: unknown;
  note: string | null;
  covered_by: string | null;
  details: Record<string, unknown>;
};

export type FuelStation = {
  id: string;
  name: string;
  brand: string | null;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  radius_m: number;
  is_trusted: boolean;
  is_active: boolean;
  notes: string | null;
  fuel_types: FuelType[];
  transactions_count: number;
  last_purchase_at: string | null;
};

export type StationPrice = {
  fuel_type: FuelType;
  unit: QuantityUnit;
  count: number;
  quantity: string;
  total_amount: string;
  average_price: string;
  min_price: string;
  max_price: string;
  last_price: string;
  fleet_average_price: string | null;
  difference_pct: string | null;
};

export type FuelStationDetail = FuelStation & {
  prices: StationPrice[];
  monthly: { month: string; fuel_type: string; average_price: string; count: number }[];
  recent: {
    id: string;
    occurred_at: string;
    vehicle: Ref;
    driver: Ref | null;
    fuel_type: string;
    quantity: string;
    unit_price: string;
    total_amount: string;
    status: RecordStatus;
    has_receipt: boolean;
  }[];
  receipts_count: number;
  pending_count: number;
};

export type ImportRow = {
  row: number;
  status: "OK" | "ERROR" | "DUPLICATE";
  messages: string[];
  warnings: string[];
  driver: string | null;
  vehicle: string | null;
  period_start: string | null;
  period_end: string | null;
  gross_earnings: string | null;
  platform_fees: string | null;
  net_earnings: string | null;
  statement_reference: string | null;
};

export type ImportPreview = {
  platform_id: string;
  file_name: string;
  headers: string[];
  mapping: Record<string, string>;
  fields: { key: string; label: string; required: boolean }[];
  rows: ImportRow[];
  counts: { OK: number; ERROR: number; DUPLICATE: number; warnings: number };
  already_imported: boolean;
};

export type ImportBatch = {
  id: string;
  platform: Ref;
  file_name: string;
  rows_total: number;
  rows_imported: number;
  skipped: { row: number; status: string; messages: string[] }[];
  status: "IMPORTED" | "VOIDED";
  created_by: { id: string; full_name: string } | null;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
  statements: Ref[];
  pending: number;
};

export type PnlPeriod = {
  period_start: string;
  period_end: string;
  gross_revenue: string;
  platform_fees: string;
  direct_operating_cost: string;
  driver_cost: string;
  net_operating_profit: string;
  shifts_count: number;
  odometer_km: number;
  loops_count: number;
  profit_per_km: string | null;
  warnings: string[];
};
