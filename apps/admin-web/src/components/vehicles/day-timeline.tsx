import clsx from "clsx";
import Link from "next/link";
import { Card, CardHeader } from "@/components/ui/card";
import { DayPicker } from "@/components/vehicles/day-picker";
import { egp } from "@/lib/cash";
import type { TimelineItem } from "@/lib/types";

const TIME = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Dot colour per kind: shift events forest, money lime-dark, problems red/amber. */
const DOT: Record<string, string> = {
  SHIFT_START: "bg-forest-800",
  SHIFT_END: "bg-forest-800",
  OPERATION: "bg-lime-400 ring-2 ring-forest-800",
  ASSIGNMENT: "bg-neutral-400",
  GPS_GAP: "bg-red-400",
  ROUTE: "bg-forest-800",
  SCHOOL_RUN: "bg-blue-400",
  FUEL: "bg-amber-400",
  EXPENSE: "bg-amber-400",
  REVENUE: "bg-lime-400",
  CLOSEOUT: "bg-lime-400",
  CASH: "bg-lime-400",
  MAINTENANCE: "bg-neutral-500",
  REVIEW: "bg-red-400",
  DAY_OFF: "bg-blue-400",
  LEDGER: "bg-neutral-500",
};

/** «يوم السيارة» (U24): everything recorded for the vehicle on one day, in order. */
export function DayTimeline({
  vehicleId,
  day,
  items,
  picker = true,
  title = "يوم السيارة",
  basePath,
  description = "كل ما سُجل للسيارة في اليوم: الورديات والتشغيل والتتبع والوقود والمصروفات والتحصيل والصيانة وحالات المراجعة.",
  empty = "لا يوجد شيء مسجل لهذه السيارة في هذا اليوم.",
}: {
  vehicleId?: string;
  day: string;
  items: TimelineItem[];
  /** Off where the day is fixed by the page (the investigation workspace). */
  picker?: boolean;
  title?: string;
  /** Page the day picker reloads (default: the vehicle page). */
  basePath?: string;
  description?: string;
  empty?: string;
}) {
  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        actions={
          picker ? (
            <DayPicker value={day} basePath={basePath ?? `/vehicles/${vehicleId}`} />
          ) : undefined
        }
      />
      {items.length === 0 ? (
        <p className="px-5 py-6 text-sm text-ink-muted">{empty}</p>
      ) : (
        <ol className="px-5 py-4">
          {items.map((it, i) => (
            <li key={`${it.kind}-${i}`} className="flex gap-3">
              <span className="flex w-12 shrink-0 justify-end pt-0.5 text-xs text-ink-muted">
                {it.at ? TIME.format(new Date(it.at)) : "اليوم"}
              </span>
              <span className="flex w-3 flex-col items-center" aria-hidden="true">
                <span
                  className={clsx(
                    "mt-1 size-2.5 shrink-0 rounded-full",
                    DOT[it.kind] ?? "bg-neutral-400",
                  )}
                />
                <span className={clsx("w-px flex-1", i === items.length - 1 ? "" : "bg-line")} />
              </span>
              <div className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 pb-3.5">
                <div className="flex min-w-0 flex-col gap-0.5">
                  {it.link ? (
                    <Link href={it.link} className="text-sm font-semibold hover:underline">
                      {it.title}
                    </Link>
                  ) : (
                    <span className="text-sm font-semibold">{it.title}</span>
                  )}
                  {it.detail ? <span className="text-xs text-ink-soft">{it.detail}</span> : null}
                  {it.until ? (
                    <span className="text-xs text-ink-muted">
                      حتى {TIME.format(new Date(it.until))}
                    </span>
                  ) : null}
                </div>
                <span className="flex items-baseline gap-2 text-xs">
                  {it.amount !== null ? (
                    <span className="font-bold">{egp(it.amount)} ج.م</span>
                  ) : null}
                  {it.status ? <span className="text-ink-muted">{it.status}</span> : null}
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
