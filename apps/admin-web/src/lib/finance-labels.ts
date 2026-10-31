import type {
  ExpenseGroup,
  FuelCategory,
  LedgerEntryType,
  PaidBy,
  PaymentMethod,
  QuantityUnit,
  ReceivedBy,
  RecordSource,
  RecordStatus,
  RevenueKind,
  SettlementStatus,
} from "./finance-types";

export const RECORD_STATUS_LABELS: Record<RecordStatus, string> = {
  SUBMITTED: "بانتظار المراجعة",
  APPROVED: "معتمد",
  REJECTED: "مرفوض",
  VOIDED: "ملغي",
};

export const RECORD_SOURCE_LABELS: Record<RecordSource, string> = {
  ADMIN: "إدخال الإدارة",
  DRIVER_APP: "تطبيق السائق",
  SYSTEM: "تلقائي من سجل آخر",
};

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH: "نقدي",
  CARD: "بطاقة",
  BANK_TRANSFER: "تحويل بنكي",
  WALLET: "محفظة إلكترونية",
  PLATFORM: "تحويل المنصة",
  OTHER: "أخرى",
};

export const PAID_BY_LABELS: Record<PaidBy, string> = {
  COMPANY: "الشركة",
  DRIVER: "السائق (يُعوَّض)",
};

export const RECEIVED_BY_LABELS: Record<ReceivedBy, string> = {
  DRIVER: "لدى السائق (عهدة)",
  COMPANY: "الشركة",
};

export const UNIT_LABELS: Record<QuantityUnit, string> = {
  LITER: "لتر",
  CUBIC_METER: "م³",
  KG: "كجم",
  UNIT: "وحدة",
};

export const FUEL_CATEGORY_LABELS: Record<FuelCategory, string> = {
  FUEL: "وقود",
  CONSUMABLE: "زيوت ومستهلكات",
};

export const EXPENSE_GROUP_LABELS: Record<ExpenseGroup, string> = {
  OPERATING: "تشغيل",
  MAINTENANCE: "صيانة",
  FINES: "مخالفات",
  OTHER: "أخرى",
};

export const REVENUE_KIND_LABELS: Record<RevenueKind, string> = {
  FIXED_ROUTE_COLLECTION: "تحصيل خط ثابت",
  CONTRACT_SERVICE: "عقد مدرسة/موظفين",
  PRIVATE_TRIP: "رحلة خاصة",
  RIDE_HAILING: "نقل ذكي",
  OTHER: "إيراد آخر",
};

export const LEDGER_TYPE_LABELS: Record<LedgerEntryType, string> = {
  EARNING: "مستحقات",
  BONUS: "مكافأة",
  REIMBURSEMENT: "تعويض مصروف",
  CASH_HANDOVER: "تسليم نقدية",
  ADVANCE: "سلفة",
  DEDUCTION: "خصم",
  PAYMENT: "صرف للسائق",
  CASH_COLLECTED: "تحصيل لدى السائق",
  ADJUSTMENT: "تسوية",
};

export const SETTLEMENT_STATUS_LABELS: Record<SettlementStatus, string> = {
  DRAFT: "مسودة",
  FINALIZED: "نهائية",
  VOIDED: "ملغاة",
};

export const options = <K extends string>(labels: Record<K, string>, exclude: K[] = []) =>
  (Object.entries(labels) as [K, string][])
    .filter(([k]) => !exclude.includes(k))
    .map(([value, label]) => ({ value, label }));
