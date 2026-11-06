import clsx from "clsx";
import Link from "next/link";
import { formatNumber } from "@/lib/format";
import type { TodayOverview } from "@/lib/types";
import { pounds } from "./operations-today";

const WEEKDAY = new Intl.DateTimeFormat("ar-EG", { weekday: "long", timeZone: "UTC" });

/** "التحصيل مقابل المصروفات": the last 7 days as paired bars, with totals that link to records. */
export function WeekFinance({ week }: { week: TodayOverview["week"] }) {
  const revenue = week.reduce((a, d) => a + Number(d.revenue), 0);
  const expenses = week.reduce((a, d) => a + Number(d.expenses), 0);
  const peak = Math.max(1, ...week.map((d) => Math.max(Number(d.revenue), Number(d.expenses))));
  const best = week.reduce((a, d) => (Number(d.revenue) > Number(a.revenue) ? d : a), week[0]!);
  const label = (iso: string) => WEEKDAY.format(new Date(`${iso}T00:00:00Z`));
  return (
    <section
      aria-label="التحصيل والمصروفات خلال 7 أيام"
      className="flex flex-wrap items-stretch gap-8 rounded-[var(--radius-panel)] border border-line bg-surface px-6 py-5"
    >
      <div className="flex flex-[1_1_240px] flex-col gap-4">
        <h2 className="text-[17px] font-bold">التحصيل مقابل المصروفات</h2>
        <span className="text-[13px] text-ink-muted">
          آخر 7 أيام · يشمل السجلات بانتظار المراجعة
        </span>
        <dl className="grid grid-cols-2 gap-3.5">
          <Link href="/finance/revenue" className="flex flex-col gap-0.5 hover:underline">
            <dt className="text-xs text-ink-muted">الإيرادات</dt>
            <dd className="text-lg font-bold">
              <span className="ltr-nums">{pounds(revenue)}</span> ج.م
            </dd>
          </Link>
          <Link href="/finance/expenses" className="flex flex-col gap-0.5 hover:underline">
            <dt className="text-xs text-ink-muted">المصروفات والوقود</dt>
            <dd className="text-lg font-bold">
              <span className="ltr-nums">{pounds(expenses)}</span> ج.م
            </dd>
          </Link>
          <div className="col-span-2 flex flex-col gap-0.5">
            <dt className="text-xs text-ink-muted">الفرق قبل مستحقات السائقين</dt>
            <dd className="text-lg font-bold text-primary">
              <span className="ltr-nums">{pounds(revenue - expenses)}</span> ج.م
            </dd>
          </div>
        </dl>
      </div>
      <div className="flex min-w-0 flex-[999_1_420px] flex-col gap-2.5">
        <div className="flex gap-4 text-xs text-ink-soft">
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="size-2.5 rounded-[3px] bg-forest-800" />
            التحصيل
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="size-2.5 rounded-[3px] bg-[#c7d3cc]" />
            المصروفات
          </span>
        </div>
        <div
          role="img"
          aria-label={`أعمدة التحصيل والمصروفات لآخر 7 أيام. أعلى تحصيل يوم ${label(best.day)}: ${formatNumber(
            Math.round(Number(best.revenue)),
          )} جنيه`}
          className="grid h-[180px] grid-cols-7 items-end gap-3 border-b border-line"
        >
          {week.map((d, i) => (
            <div key={d.day} className="flex h-full items-end justify-center gap-1">
              <div
                className={clsx(
                  "w-[40%] max-w-[22px] rounded-t-md",
                  i === week.length - 1 ? "bg-forest-800" : "bg-forest-600",
                )}
                style={{ height: `${(Number(d.revenue) / peak) * 100}%` }}
              />
              <div
                className="w-[40%] max-w-[22px] rounded-t-md bg-[#c7d3cc]"
                style={{ height: `${(Number(d.expenses) / peak) * 100}%` }}
              />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-3 text-center text-xs text-ink-muted">
          {week.map((d, i) => (
            <span
              key={d.day}
              className={i === week.length - 1 ? "font-bold text-primary" : undefined}
            >
              {label(d.day)}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
