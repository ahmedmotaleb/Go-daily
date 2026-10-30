/** Arabic labels for API enums. Keys must match the API values. */

export const OWNERSHIP_LABELS_AR = {
  OWNED: "ملك الشركة",
  LEASED: "إيجار",
  PARTNER: "شراكة / مستثمر",
  DRIVER_OWNED: "ملك السائق",
  OTHER: "أخرى",
} as const;
export type OwnershipStatus = keyof typeof OWNERSHIP_LABELS_AR;

export const EMPLOYMENT_STATUS_LABELS_AR = {
  ACTIVE: "يعمل",
  ON_LEAVE: "إجازة",
  SUSPENDED: "موقوف",
  TERMINATED: "انتهى التعاقد",
} as const;
export type EmploymentStatus = keyof typeof EMPLOYMENT_STATUS_LABELS_AR;

export const EXPIRY_STATUS_LABELS_AR = {
  OK: "سارية",
  EXPIRING_SOON: "تنتهي قريبًا",
  EXPIRED: "منتهية",
  UNKNOWN: "غير مسجلة",
} as const;
export type ExpiryStatus = keyof typeof EXPIRY_STATUS_LABELS_AR;

export const COMPENSATION_METHOD_LABELS_AR = {
  FIXED_MONTHLY: "راتب شهري ثابت",
  DAILY_WAGE: "يومية",
  REVENUE_PERCENTAGE: "نسبة من الإيراد",
  FIXED_PLUS_INCENTIVE: "ثابت + حافز",
} as const;
export type CompensationMethod = keyof typeof COMPENSATION_METHOD_LABELS_AR;

export const ASSIGNMENT_ROLE_LABELS_AR = {
  PRIMARY: "سائق أساسي",
  RELIEF: "سائق بديل / وردية ثانية",
} as const;
export type AssignmentRole = keyof typeof ASSIGNMENT_ROLE_LABELS_AR;

export function options<T extends Record<string, string>>(labels: T): { value: keyof T & string; label: string }[] {
  return Object.entries(labels).map(([value, label]) => ({ value: value as keyof T & string, label }));
}
