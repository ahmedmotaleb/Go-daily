/**
 * Admin navigation. `permission` hides items the user cannot use; the API
 * still enforces access. Items with `soon: true` are modules not yet built.
 */
export type NavIcon =
  | "dashboard"
  | "fleet"
  | "drivers"
  | "operations"
  | "shifts"
  | "map"
  | "collections"
  | "rides"
  | "wallet"
  | "profit"
  | "expenses"
  | "fuel"
  | "maintenance"
  | "reports"
  | "alerts"
  | "review"
  | "users"
  | "settings";

export type NavItem = {
  href: string;
  label: string;
  icon: NavIcon;
  permission?: string;
  soon?: boolean;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "لوحة التحكم", icon: "dashboard" },
  { href: "/vehicles", label: "الأسطول", icon: "fleet", permission: "vehicles:read" },
  { href: "/drivers", label: "السائقون", icon: "drivers", permission: "drivers:read" },
  {
    href: "/operations",
    label: "التشغيل",
    icon: "operations",
    permission: "operations:read",
  },
  { href: "/shifts", label: "الورديات", icon: "shifts", permission: "shifts:read" },
  { href: "/finance/fuel", label: "الوقود والزيوت", icon: "fuel", permission: "fuel:read" },
  {
    href: "/finance/expenses",
    label: "المصروفات",
    icon: "expenses",
    permission: "expenses:read",
  },
  {
    href: "/finance/revenue",
    label: "الإيرادات والتحصيل",
    icon: "collections",
    permission: "revenue:read",
  },
  {
    href: "/finance/ride-hailing",
    label: "النقل الذكي",
    icon: "rides",
    permission: "revenue:read",
  },
  {
    href: "/finance/settlements",
    label: "تسويات السائقين",
    icon: "wallet",
    permission: "settlements:read",
  },
  {
    href: "/finance/profitability",
    label: "ربحية المركبات",
    icon: "profit",
    permission: "profitability:read",
  },
  {
    href: "/maintenance",
    label: "الصيانة",
    icon: "maintenance",
    permission: "maintenance:read",
  },
  { href: "/reports", label: "التقارير", icon: "reports", permission: "reports:read" },
  {
    href: "/exceptions",
    label: "حالات للمراجعة",
    icon: "review",
    permission: "exceptions:read",
  },
  {
    href: "/notifications",
    label: "التنبيهات",
    icon: "alerts",
    permission: "notifications:read",
  },
  { href: "/users", label: "المستخدمون", icon: "users", permission: "users:read" },
  {
    href: "/finance/settings",
    label: "إعدادات المالية",
    icon: "settings",
    permission: "settings:manage",
  },
];

export function navForPermissions(permissions: string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
