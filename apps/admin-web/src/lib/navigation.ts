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
  | "expenses"
  | "fuel"
  | "maintenance"
  | "reports"
  | "alerts"
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
  {
    href: "/collections",
    label: "التحصيلات",
    icon: "collections",
    permission: "revenue:read",
    soon: true,
  },
  {
    href: "/expenses",
    label: "المصروفات",
    icon: "expenses",
    permission: "expenses:read",
    soon: true,
  },
  {
    href: "/maintenance",
    label: "الصيانة",
    icon: "maintenance",
    permission: "maintenance:read",
    soon: true,
  },
  { href: "/reports", label: "التقارير", icon: "reports", permission: "reports:read", soon: true },
  {
    href: "/alerts",
    label: "التنبيهات",
    icon: "alerts",
    permission: "exceptions:read",
    soon: true,
  },
  { href: "/users", label: "المستخدمون", icon: "users", permission: "users:read" },
  {
    href: "/settings",
    label: "الإعدادات",
    icon: "settings",
    permission: "settings:manage",
    soon: true,
  },
];

export function navForPermissions(permissions: string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
}

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
