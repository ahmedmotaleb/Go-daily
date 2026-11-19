import {
  Banknote,
  Bus,
  CalendarDays,
  ChartColumn,
  Clock,
  Fuel,
  ShieldAlert,
  UsersRound,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { FleetNow } from "@/components/dashboard/fleet-now";
import { KpiCard } from "@/components/dashboard/kpi-card";
import { OperationsToday, pounds } from "@/components/dashboard/operations-today";
import { ReviewPanel } from "@/components/dashboard/review-panel";
import { WeekFinance } from "@/components/dashboard/week-finance";
import { ExpiryBadge } from "@/components/domain/badges";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { actionLabel } from "@/lib/audit-labels";
import { can, getCurrentUser } from "@/lib/auth";
import type { ExceptionSummary, OperationalException } from "@/lib/exception-types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { tileConfig } from "@/lib/map-config";
import type { DashboardSummary, LivePosition, Page, TodayOverview } from "@/lib/types";

export const metadata: Metadata = { title: "لوحة التشغيل" };

const DOC_LABELS: Record<DashboardSummary["expiring_documents"][number]["kind"], string> = {
  VEHICLE_LICENSE: "رخصة مركبة",
  VEHICLE_INSURANCE: "تأمين مركبة",
  DRIVER_LICENSE: "رخصة قيادة",
};

const ENTITY_PATHS: Record<string, string> = {
  vehicle: "/vehicles",
  driver: "/drivers",
  shift: "/shifts",
  route: "/operations/routes",
};

const TIME = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export default async function DashboardPage() {
  const user = await getCurrentUser();
  const canTrack = can(user, "tracking:read");
  const canReview = can(user, "exceptions:read");
  const [data, today, live, summary, cases] = await Promise.all([
    api.get<DashboardSummary>("/dashboard/summary"),
    api.get<TodayOverview>("/dashboard/today"),
    canTrack ? api.get<LivePosition[]>("/tracking/live") : Promise.resolve(null),
    canReview ? api.get<ExceptionSummary>("/exceptions/summary") : Promise.resolve(null),
    canReview
      ? api.get<Page<OperationalException>>("/exceptions", { status: "ACTIVE", page_size: 5 })
      : Promise.resolve(null),
  ]);
  const { kpis } = data;
  const idle = Math.max(0, kpis.active_vehicles - kpis.active_shifts);
  const expenses =
    today.fuel && today.other_expenses
      ? Number(today.fuel.total) + Number(today.other_expenses.total)
      : null;
  const pendingRevenue = today.revenue ? Number(today.revenue.pending) : 0;

  return (
    <>
      <PageHeader
        title="لوحة التشغيل"
        description={`آخر تحديث ${TIME.format(new Date(data.generated_at))}`}
      />

      <div className="flex flex-col gap-6">
        <section
          aria-label="المؤشرات الرئيسية"
          className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-4"
        >
          <KpiCard
            label="السيارات في وردية"
            value={formatNumber(kpis.active_shifts)}
            unit={`من ${formatNumber(kpis.active_vehicles)}`}
            sub={idle ? `${formatNumber(idle)} بدون وردية الآن` : "كل السيارات النشطة في وردية"}
            icon={Bus}
          />
          <KpiCard
            label="الورديات الحالية"
            value={formatNumber(kpis.active_shifts)}
            unit="وردية"
            sub={
              today.oldest_shift_started_at
                ? `أقدمها بدأت ${TIME.format(new Date(today.oldest_shift_started_at))}`
                : "لا توجد ورديات جارية"
            }
            icon={Clock}
          />
          {today.revenue ? (
            <KpiCard
              label="تحصيل اليوم"
              value={pounds(today.revenue.total)}
              unit="ج.م"
              sub={
                pendingRevenue
                  ? `منها ${pounds(pendingRevenue)} بانتظار المراجعة`
                  : "كل السجلات معتمدة"
              }
              icon={Banknote}
              href="/finance/revenue"
            />
          ) : (
            <KpiCard
              label="ورديات اليوم"
              value={formatNumber(kpis.today_shifts)}
              unit="وردية"
              icon={CalendarDays}
            />
          )}
          {expenses !== null && today.fuel && today.other_expenses ? (
            <KpiCard
              label="مصروفات اليوم"
              value={pounds(expenses)}
              unit="ج.م"
              sub={`وقود ${pounds(today.fuel.total)} · أخرى ${pounds(today.other_expenses.total)}`}
              icon={Fuel}
              href="/finance/expenses"
            />
          ) : (
            <KpiCard
              label="السائقون النشطون"
              value={formatNumber(kpis.active_drivers)}
              unit="سائق"
              icon={UsersRound}
            />
          )}
          {today.revenue && expenses !== null ? (
            <KpiCard
              label="صافي التشغيل"
              value={pounds(Number(today.revenue.total) - expenses)}
              unit="ج.م"
              sub="قبل مستحقات السائقين"
              icon={ChartColumn}
              tone="hero"
            />
          ) : null}
          {summary ? (
            <KpiCard
              label="حالات تحتاج مراجعة"
              value={formatNumber(summary.active)}
              unit="حالة"
              sub={`${formatNumber(summary.by_severity.HIGH ?? 0)} أولوية عالية`}
              icon={ShieldAlert}
              tone={summary.active ? "alert" : "default"}
              href="/exceptions"
            />
          ) : null}
        </section>

        {live || (summary && cases) ? (
          <div className="flex flex-wrap items-stretch gap-6">
            {live ? (
              <div className="min-w-0 flex-[999_1_620px]">
                <FleetNow tiles={tileConfig()} vehicles={data.vehicles} initial={live} />
              </div>
            ) : null}
            {summary && cases ? (
              <div className="flex min-w-0 flex-[1_1_340px]">
                <ReviewPanel total={summary.active} cases={cases.items} />
              </div>
            ) : null}
          </div>
        ) : null}

        <OperationsToday operations={today.operations} />

        {today.week.length ? <WeekFinance week={today.week} /> : null}

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="رخص وتأمينات تحتاج متابعة" />
            {data.expiring_documents.length === 0 ? (
              <p className="px-5 py-4 text-sm text-ink-muted">
                لا توجد مستندات منتهية أو قريبة الانتهاء.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {data.expiring_documents.map((d) => (
                  <li
                    key={`${d.kind}-${d.entity_id}`}
                    className="flex items-start justify-between gap-3 px-5 py-3 text-sm"
                  >
                    <div>
                      <Link
                        href={`/${d.entity_type === "vehicle" ? "vehicles" : "drivers"}/${d.entity_id}`}
                        className="font-medium hover:underline"
                      >
                        {d.label}
                      </Link>
                      <p className="text-xs text-ink-muted">{DOC_LABELS[d.kind]}</p>
                    </div>
                    <ExpiryBadge status={d.status} date={d.expires_on} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="آخر النشاطات" />
            {data.recent_activity.length === 0 ? (
              <p className="px-5 py-4 text-sm text-ink-muted">لا توجد نشاطات بعد.</p>
            ) : (
              <ol className="divide-y divide-line">
                {data.recent_activity.slice(0, 8).map((a) => {
                  const base = a.entity_type ? ENTITY_PATHS[a.entity_type] : undefined;
                  const label = actionLabel(a.action);
                  return (
                    <li key={a.id} className="px-5 py-3 text-sm">
                      {base && a.entity_id ? (
                        <Link
                          href={`${base}/${a.entity_id}`}
                          className="font-medium hover:underline"
                        >
                          {label}
                        </Link>
                      ) : (
                        <span className="font-medium">{label}</span>
                      )}
                      <p className="text-xs text-ink-muted">
                        {formatDateTime(a.occurred_at)}
                        {a.actor_name ? ` · ${a.actor_name}` : ""}
                      </p>
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
