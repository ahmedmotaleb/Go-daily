import clsx from "clsx";
import {
  Banknote,
  Clock,
  Fuel,
  Gauge,
  SignalLow,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { formatDateTime } from "@/lib/format";
import type { ExceptionSeverity, OperationalException } from "@/lib/exception-types";

const SEVERITY: Record<ExceptionSeverity, { label: string; badge: string; tile: string }> = {
  HIGH: { label: "عالية", badge: "bg-danger-soft text-danger", tile: "bg-danger-soft text-danger" },
  MEDIUM: {
    label: "متوسطة",
    badge: "bg-warning-soft text-warning",
    tile: "bg-warning-soft text-warning",
  },
  LOW: {
    label: "منخفضة",
    badge: "bg-neutral-100 text-neutral-700",
    tile: "bg-neutral-100 text-neutral-700",
  },
};

/** Icon by the kind of rule: GPS, fuel, odometer, money, schedule, anything else. */
export function ruleIcon(code: string): LucideIcon {
  if (/GPS|TRACKING|MOCK|JUMP|TIMESTAMP|LATE_GPS|OUT_OF_SHIFT/.test(code)) return SignalLow;
  if (code.startsWith("FUEL")) return Fuel;
  if (/ODOMETER|MOVED/.test(code)) return Gauge;
  if (/COLLECTION|REVENUE|DUPLICATE_TRANSACTION/.test(code)) return Banknote;
  if (/STOP|SCHOOL|DEVIATION/.test(code)) return Clock;
  return TriangleAlert;
}

/** "حالات تحتاج مراجعة": the latest open review cases with their severity. */
export function ReviewPanel({ total, cases }: { total: number; cases: OperationalException[] }) {
  return (
    <section
      aria-label="حالات تحتاج مراجعة"
      className="flex min-w-0 flex-col rounded-[var(--radius-panel)] border border-line bg-surface shadow-[var(--shadow-panel)]"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div className="flex items-center gap-2.5">
          <h2 className="text-[17px] font-bold">حالات تحتاج مراجعة</h2>
          <span className="ltr-nums rounded-full bg-danger-soft px-2.5 text-xs leading-5 font-bold text-danger">
            {total}
          </span>
        </div>
        <Link href="/exceptions" className="text-[13px] font-semibold text-primary hover:underline">
          مركز المراجعة
        </Link>
      </div>
      {cases.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-ink-muted">لا توجد حالات مفتوحة الآن.</p>
      ) : (
        <ul>
          {cases.map((c) => {
            const Icon = ruleIcon(c.rule_code);
            const sev = SEVERITY[c.severity];
            return (
              <li key={c.id} className="border-b border-neutral-100">
                <Link
                  href={`/exceptions/${c.id}`}
                  className="flex items-start gap-3 px-5 py-3.5 hover:bg-neutral-50"
                >
                  <span
                    aria-hidden="true"
                    className={clsx(
                      "flex size-9 shrink-0 items-center justify-center rounded-[10px]",
                      sev.tile,
                    )}
                  >
                    <Icon className="size-[18px]" strokeWidth={1.8} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold">{c.rule_title}</span>
                      <span
                        className={clsx(
                          "rounded-full px-2 text-[11px] leading-5 font-bold whitespace-nowrap",
                          sev.badge,
                        )}
                      >
                        {sev.label}
                      </span>
                    </span>
                    <span className="text-[13px] text-ink-soft">{c.summary}</span>
                    <span className="text-xs text-ink-muted">
                      {[c.vehicle?.name, c.driver?.name, formatDateTime(c.occurred_at)]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-auto px-5 py-3.5">
        <Link
          href="/exceptions?status=ACTIVE"
          className="flex h-11 items-center justify-center rounded-[var(--radius-control)] border border-line text-sm font-semibold text-primary hover:bg-neutral-50"
        >
          عرض كل الحالات المفتوحة
        </Link>
      </div>
    </section>
  );
}
