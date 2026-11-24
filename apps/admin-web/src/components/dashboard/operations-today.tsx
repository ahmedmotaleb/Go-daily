import clsx from "clsx";
import {
  CarTaxiFront,
  Flag,
  GraduationCap,
  Route,
  UsersRound,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { formatNumber } from "@/lib/format";
import type { TodayOverview } from "@/lib/types";

const ICONS: Record<string, LucideIcon> = {
  RIDE_HAILING: CarTaxiFront,
  FIXED_ROUTE: Route,
  SCHOOL_ROUTE: GraduationCap,
  PRIVATE_TRIP: Flag,
  EMPLOYEE_TRANSPORT: UsersRound,
};

/** Whole pounds for summary figures ("2,940"); details pages keep piastres. */
export function pounds(value: string | number): string {
  return formatNumber(Math.round(Number(value)));
}

/** "العمليات اليوم": one card per operation type with real activity today. */
export function OperationsToday({ operations }: { operations: TodayOverview["operations"] }) {
  return (
    <section aria-label="ملخص العمليات" className="flex flex-col gap-3.5">
      <h2 className="text-lg font-bold">العمليات اليوم</h2>
      {operations.length === 0 ? (
        <p className="rounded-[18px] border border-line bg-surface px-5 py-6 text-sm text-ink-muted">
          لا توجد تشغيلات مسجلة اليوم.
        </p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
          {operations.map((o) => {
            const Icon = ICONS[o.kind] ?? Waypoints;
            return (
              <div
                key={o.kind}
                className="flex flex-col gap-4 rounded-[18px] border border-line bg-surface p-5 shadow-[var(--shadow-card)]"
              >
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="flex size-10 items-center justify-center rounded-[var(--radius-control)] bg-forest-50 text-forest-800"
                  >
                    <Icon className="size-5" strokeWidth={1.7} />
                  </span>
                  <div className="flex flex-1 flex-col gap-0.5">
                    <span className="text-[15px] font-bold">{o.name_ar}</span>
                    <span className="text-xs text-ink-muted">
                      {o.vehicles} سيارة · {o.sessions_today} تشغيل اليوم
                    </span>
                  </div>
                </div>
                <div className="flex items-end justify-between gap-3">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs text-ink-muted">{o.activity_label}</span>
                    <span className="ltr-nums text-[22px] font-bold text-primary">
                      {o.activity_value}
                    </span>
                  </div>
                  {o.collection !== null ? (
                    <div className="flex flex-col gap-0.5 text-left">
                      <span className="text-xs text-ink-muted">التحصيل</span>
                      <span className="text-base font-bold">
                        <span className="ltr-nums">{pounds(o.collection)}</span>{" "}
                        <span className="text-xs font-medium text-ink-muted">ج.م</span>
                      </span>
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-col gap-1.5">
                  {o.progress_pct !== null ? (
                    <div
                      className="h-1.5 overflow-hidden rounded-full bg-neutral-100"
                      aria-hidden="true"
                    >
                      <div
                        className={clsx(
                          "h-full rounded-full",
                          o.note_is_warning ? "bg-amber-400" : "bg-forest-800",
                        )}
                        style={{ width: `${o.progress_pct}%` }}
                      />
                    </div>
                  ) : null}
                  {o.note ? (
                    <span
                      className={clsx(
                        "text-xs",
                        o.note_is_warning ? "text-warning" : "text-ink-muted",
                      )}
                    >
                      {o.note}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
