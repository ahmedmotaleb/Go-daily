import clsx from "clsx";
import type { Metadata } from "next";
import Link from "next/link";
import { AutoRefresh } from "@/components/tracking/auto-refresh";
import { WorkspaceBar } from "@/components/tracking/workspace-bar";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { egp } from "@/lib/cash";
import { FLEET_STATUS, fleetStatus, sinceText } from "@/lib/fleet-status";
import { formatNumber } from "@/lib/format";
import type { ControlCenter, ControlRow } from "@/lib/types";

export const metadata: Metadata = { title: "مركز التحكم التشغيلي" };

const TIME = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function Cell({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex min-w-0 flex-col gap-0.5", className)}>
      <span className="text-[11px] text-ink-muted">{label}</span>
      <span className="text-sm font-semibold">{children}</span>
    </div>
  );
}

function Row({ r, now }: { r: ControlRow; now: number }) {
  const status = FLEET_STATUS[fleetStatus(r.tracking_state)];
  return (
    <article className="grid grid-cols-2 gap-x-5 gap-y-3 rounded-[18px] border border-line bg-surface px-5 py-4 sm:grid-cols-4 xl:grid-cols-[1.4fr_1.2fr_1fr_0.8fr_0.8fr_0.9fr_0.9fr_1.4fr]">
      <div className="col-span-2 flex min-w-0 flex-col gap-0.5 sm:col-span-4 xl:col-span-1">
        <span className="text-base font-bold">{r.plate_number}</span>
        <span className="truncate text-xs text-ink-soft">
          {r.driver_name} · {r.vehicle_code}
        </span>
      </div>
      <Cell label="التشغيل">{r.operation ?? <span className="text-ink-muted">لم يُحدد</span>}</Cell>
      <div className="flex flex-col gap-1">
        <Badge tone={status.tone} dot className="self-start">
          {status.label}
        </Badge>
        <span className="text-[11px] text-ink-muted">
          {r.last_received_at ? `آخر موقع ${sinceText(r.last_received_at, now)}` : "لم يصل أي موقع"}
          {r.speed_kmh !== null ? ` · ${Math.round(r.speed_kmh)} كم/س` : ""}
        </span>
      </div>
      <Cell label="بداية الوردية">
        {r.shift_started_at ? TIME.format(new Date(r.shift_started_at)) : "—"}
      </Cell>
      <Cell label="دورات · اتجاهات">
        {formatNumber(r.loops)} · {formatNumber(r.legs)}
      </Cell>
      <Cell label="دورات المدارس">
        {r.school_planned ? (
          <>
            {formatNumber(r.school_done)} / {formatNumber(r.school_planned)}
            {r.school_attention ? (
              <span className="ms-1 text-xs text-warning">({r.school_attention} تحتاج مراجعة)</span>
            ) : null}
          </>
        ) : (
          "—"
        )}
      </Cell>
      <Cell label="تحصيل · وقود اليوم">
        {r.collection_today !== null ? egp(r.collection_today) : "—"} ·{" "}
        {r.fuel_today !== null ? egp(r.fuel_today) : "—"}
      </Cell>
      <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-4 xl:col-span-1">
        {r.open_cases === null ? null : r.open_cases ? (
          <Link
            href={`/exceptions?vehicle_id=${r.vehicle_id}`}
            className="flex flex-col gap-0.5 rounded-[10px] bg-warning-soft px-2.5 py-1.5 text-xs text-warning hover:underline"
          >
            <span className="font-bold">{formatNumber(r.open_cases)} حالات مراجعة</span>
            <span className="truncate">{r.case_titles[0]}</span>
          </Link>
        ) : (
          <span className="text-xs text-ink-muted">لا توجد حالات مفتوحة</span>
        )}
        <Link
          href={`/tracking?shift=${r.shift_id}`}
          className="text-xs font-semibold text-primary hover:underline"
        >
          عرض المسار ←
        </Link>
      </div>
    </article>
  );
}

export default async function ControlPage() {
  await requirePermission("tracking:read");
  const data = await api.get<ControlCenter>("/dashboard/control");
  const now = new Date(data.generated_at).getTime();
  const counts = data.rows.reduce<Record<string, number>>((acc, r) => {
    acc[r.tracking_state] = (acc[r.tracking_state] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <>
      <WorkspaceBar title="مركز التحكم التشغيلي">
        <span className="text-[13px] text-[#c9d6d0]">
          تحديث تلقائي كل 30 ثانية · آخر تحديث {TIME.format(new Date(data.generated_at))}
        </span>
      </WorkspaceBar>
      <AutoRefresh seconds={30} />
      <main
        id="main"
        className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 pt-6 pb-12 sm:px-6"
      >
        <ul className="flex flex-wrap gap-4 text-sm text-ink-soft" aria-label="ملخص">
          <li>
            <strong className="text-ink">{formatNumber(data.rows.length)}</strong> سيارة في وردية
          </li>
          <li>
            <strong className="text-ink">{formatNumber(counts.ONLINE ?? 0)}</strong> يتم تتبعها
          </li>
          <li>
            <strong className="text-warning">{formatNumber(counts.STALE ?? 0)}</strong> موقع لم
            يتحدث
          </li>
          <li>
            <strong className="text-danger">{formatNumber(counts.OFFLINE ?? 0)}</strong> انقطاع GPS
          </li>
        </ul>
        {data.rows.length === 0 ? (
          <EmptyState
            title="لا توجد سيارات في وردية الآن"
            description="تظهر هنا كل سيارة تبدأ وردية، مع التتبع والتشغيل والتحصيل وحالات المراجعة."
          />
        ) : (
          data.rows.map((r) => <Row key={r.shift_id} r={r} now={now} />)
        )}
        <p className="text-xs text-ink-muted">
          كل الأرقام مسجلة فعليًا: لا يُعرض موقع لم يصل، والتحصيل والوقود يشملان السجلات بانتظار
          المراجعة. انقطاع الإشارة لا يعني بالضرورة وجود مشكلة.
        </p>
      </main>
    </>
  );
}
