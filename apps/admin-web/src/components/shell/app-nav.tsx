"use client";

import clsx from "clsx";
import {
  Banknote,
  Bell,
  Bus,
  CarTaxiFront,
  Clock,
  Fuel,
  LayoutDashboard,
  Map,
  Menu,
  Receipt,
  Route,
  FileBarChart,
  Settings,
  ShieldAlert,
  TrendingUp,
  UserCog,
  UsersRound,
  Wallet,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Logo } from "@/components/logo";
import { isActivePath, type NavIcon, type NavItem } from "@/lib/navigation";

const ICONS: Record<NavIcon, LucideIcon> = {
  dashboard: LayoutDashboard,
  fleet: Bus,
  drivers: UsersRound,
  operations: Route,
  shifts: Clock,
  map: Map,
  collections: Banknote,
  rides: CarTaxiFront,
  wallet: Wallet,
  profit: TrendingUp,
  expenses: Receipt,
  fuel: Fuel,
  maintenance: Wrench,
  reports: FileBarChart,
  alerts: Bell,
  review: ShieldAlert,
  users: UserCog,
  settings: Settings,
};

function NavList({
  items,
  badges,
  onNavigate,
}: {
  items: NavItem[];
  badges: Record<string, number>;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const Icon = ICONS[item.icon];
        const active = !item.soon && isActivePath(pathname, item.href);
        const badge = badges[item.href] ?? 0;
        if (item.soon) {
          return (
            <li key={item.href}>
              <span
                className="flex min-h-10 cursor-default items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm text-forest-200/60"
                aria-disabled="true"
              >
                <Icon className="size-5 shrink-0" strokeWidth={1.7} aria-hidden="true" />
                <span className="flex-1">{item.label}</span>
                <span className="rounded-full bg-forest-800 px-2 py-0.5 text-[10px] text-forest-200">
                  قريبًا
                </span>
              </span>
            </li>
          );
        }
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "flex min-h-10 items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-forest-800 font-semibold text-white shadow-[inset_-3px_0_0_var(--color-lime-400)]"
                  : "font-medium text-[#c9d6d0] hover:bg-forest-800/70 hover:text-white",
              )}
            >
              <Icon className="size-5 shrink-0" strokeWidth={1.7} aria-hidden="true" />
              <span className="flex-1">{item.label}</span>
              {badge > 0 ? (
                <span className="ltr-nums rounded-full bg-lime-400 px-2 text-xs leading-5 font-bold text-forest-900">
                  <span className="sr-only">عدد الحالات المفتوحة: </span>
                  {badge > 99 ? "99+" : badge}
                </span>
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** Initials of the first two words of a name ("إدارة التشغيل" -> "إ ت"). */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join(" ");
}

function UserBlock({ name, role }: { name: string; role: string }) {
  return (
    <div className="flex items-center gap-2.5 border-t border-white/10 px-2 pt-4">
      <span
        aria-hidden="true"
        className="flex size-9 items-center justify-center rounded-full border border-forest-600 bg-forest-800 text-sm font-semibold text-white"
      >
        {initials(name)}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-semibold text-white">{name}</span>
        <span className="text-xs text-[#a9bdb5]">صلاحية: {role}</span>
      </span>
    </div>
  );
}

export function AppNav({
  items,
  badges = {},
  userName,
  roleLabel,
}: {
  items: NavItem[];
  badges?: Record<string, number>;
  userName: string;
  roleLabel: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {/* Desktop sidebar (right in RTL) */}
      <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col gap-6 bg-sidebar px-4 py-6 text-white lg:flex">
        <div className="px-2 pb-2">
          <Logo inverted tagline width={184} />
        </div>
        <nav aria-label="القائمة الرئيسية" className="-mx-1 flex-1 overflow-y-auto px-1">
          <NavList items={items} badges={badges} />
        </nav>
        <UserBlock name={userName} role={roleLabel} />
      </aside>

      {/* Mobile top bar + drawer */}
      <div className="flex items-center justify-between bg-sidebar px-4 py-3 lg:hidden">
        <Logo inverted width={96} />
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex size-11 items-center justify-center rounded-[var(--radius-control)] text-white hover:bg-forest-800"
          aria-label="فتح القائمة"
          aria-expanded={open}
        >
          <Menu className="size-5" />
        </button>
      </div>
      {open ? (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="القائمة"
        >
          <button
            type="button"
            className="absolute inset-0 bg-forest-900/50"
            aria-label="إغلاق القائمة"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-y-0 start-0 flex w-72 flex-col gap-4 bg-sidebar px-4 py-4">
            <div className="flex items-center justify-between px-1">
              <Logo inverted width={110} />
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex size-11 items-center justify-center rounded-[var(--radius-control)] text-white hover:bg-forest-800"
                aria-label="إغلاق القائمة"
              >
                <X className="size-5" />
              </button>
            </div>
            <nav aria-label="القائمة الرئيسية" className="flex-1 overflow-y-auto">
              <NavList items={items} badges={badges} onNavigate={() => setOpen(false)} />
            </nav>
            <UserBlock name={userName} role={roleLabel} />
          </div>
        </div>
      ) : null}
    </>
  );
}
