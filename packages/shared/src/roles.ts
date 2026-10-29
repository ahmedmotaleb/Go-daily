/** User roles. Must match the API's `UserRole` enum. */
export const ROLES = ["SUPER_ADMIN", "ADMIN", "OPERATIONS", "ACCOUNTANT", "DRIVER"] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_LABELS_AR: Record<Role, string> = {
  SUPER_ADMIN: "مدير عام",
  ADMIN: "مدير",
  OPERATIONS: "تشغيل",
  ACCOUNTANT: "محاسب",
  DRIVER: "سائق",
};
