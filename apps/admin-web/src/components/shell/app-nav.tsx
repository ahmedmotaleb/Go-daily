"use client";

import clsx from "clsx";
import {
  Banknote,
  Bell,
  Bus,
  Clock,
  Fuel,
  LayoutDashboard,
  Map,
  Menu,
  Receipt,
  Route,
  FileBarChart,
  Settings,
  UserCog,
  UsersRound,
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
  expenses: Receipt,
  fuel: Fuel,
  maintenance: Wrench,
  reports: FileBarChart,
  alerts: Bell,
  users: UserCog,
  settings: Settings,
};

function NavList({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const Icon = ICONS[item.icon];
        const active = !item.soon && isActivePath(pathname, item.href);
        if (item.soon) {
          return (
            <li key={item.href}>
              <span
                className="flex cursor-default items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 text-sm text-forest-200/60"
                aria-disabled="true"
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                <span className="flex-1">{item.label}</span>
                <span className="rounded-full bg-forest-900 px-2 py-0.5 text-[10px] text-forest-200">
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
                "flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-forest-700 font-semibold text-white shadow-[inset_-3px_0_0_var(--color-lime-400)]"
                  : "text-forest-100 hover:bg-forest-700/60 hover:text-white",
              )}
            >
              <Icon
                className={clsx("size-4 shrink-0", active && "text-lime-400")}
                aria-hidden="true"
              />
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function AppNav({ items }: { items: NavItem[] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-forest-800 lg:flex">
        <div className="px-5 py-5">
          <Logo inverted />
        </div>
        <nav aria-label="القائمة الرئيسية" className="flex-1 overflow-y-auto px-3 pb-6">
          <NavList items={items} />
        </nav>
      </aside>

      {/* Mobile top bar + drawer */}
      <div className="flex items-center justify-between bg-forest-800 px-4 py-3 lg:hidden">
        <Logo inverted />
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-[var(--radius-control)] p-2 text-white hover:bg-forest-700"
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
            className="absolute inset-0 bg-neutral-950/40"
            aria-label="إغلاق القائمة"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-y-0 start-0 flex w-72 flex-col bg-forest-800">
            <div className="flex items-center justify-between px-5 py-4">
              <Logo inverted />
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-[var(--radius-control)] p-2 text-white hover:bg-forest-700"
                aria-label="إغلاق القائمة"
              >
                <X className="size-5" />
              </button>
            </div>
            <nav aria-label="القائمة الرئيسية" className="flex-1 overflow-y-auto px-3 pb-6">
              <NavList items={items} onNavigate={() => setOpen(false)} />
            </nav>
          </div>
        </div>
      ) : null}
    </>
  );
}
