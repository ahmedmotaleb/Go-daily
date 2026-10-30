import type { Metadata } from "next";
import Link from "next/link";
import { FilterBar } from "@/components/finance/filters";
import { RecordStatusBadge } from "@/components/finance/review";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { Reconciliation, ReconciliationRow } from "@/lib/finance-types";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { cairoToday, spDate, spUuid } from "@/lib/search";

export const metadata: Metadata = { title: "مطابقة النقل الذكي" };

function minutes(m: number) {
  const h = Math.floor(m / 60);
  return h ? `${h} س ${m % 60} د` : `${m} د`;
}

function Rows({ rows, withStatement }: { rows: ReconciliationRow[]; withStatement: boolean }) {
  return (
    <Table>
      <THead>
        <tr>
          <TH>الفترة</TH>
          <TH>السائق / المركبة</TH>
          {withStatement ? <TH>الكشف</TH> : null}
          <TH>ورديات</TH>
          <TH>وقت النقل الذكي</TH>
          <TH>العداد</TH>
          <TH>GPS</TH>
          {withStatement ? <TH>صافي/ساعة</TH> : null}
          {withStatement ? <TH>صافي/كم</TH> : null}
          <TH>ملاحظات</TH>
        </tr>
      </THead>
      <tbody>
        {rows.map((r, i) => (
          <TR key={r.statement?.id ?? `${r.driver.id}-${i}`}>
            <TD>
              {r.statement ? (
                <Link
                  href={`/finance/ride-hailing/${r.statement.id}`}
                  className="font-semibold text-forest-700 hover:underline"
                >
                  {formatDate(r.period_start)} — {formatDate(r.period_end)}
                </Link>
              ) : (
                `${formatDate(r.period_start)} — ${formatDate(r.period_end)}`
              )}
            </TD>
            <TD>
              {r.driver.name}
              <span className="ltr-nums block text-xs text-ink-muted">{r.vehicle.name}</span>
            </TD>
            {withStatement && r.statement ? (
              <TD>
                <span className="ltr-nums block">{formatMoney(r.statement.net_earnings)}</span>
                <span className="text-xs text-ink-muted">
                  {formatNumber(r.statement.trips_count)} رحلة · {r.statement.platform.name}
                </span>
                <RecordStatusBadge status={r.statement.status} />
              </TD>
            ) : null}
            <TD className="ltr-nums">{formatNumber(r.shifts_count)}</TD>
            <TD>{minutes(r.ride_hailing_minutes)}</TD>
            <TD className="ltr-nums">
              {r.odometer_km === null ? "—" : `${formatNumber(r.odometer_km)} كم`}
            </TD>
            <TD className="ltr-nums">{r.gps_km === null ? "—" : `${formatNumber(r.gps_km)} كم`}</TD>
            {withStatement ? <TD className="ltr-nums">{formatMoney(r.net_per_hour)}</TD> : null}
            {withStatement ? <TD className="ltr-nums">{formatMoney(r.net_per_km)}</TD> : null}
            <TD>
              <div className="flex flex-col gap-1">
                {r.flags.length === 0 ? <span className="text-ink-muted">—</span> : null}
                {r.flags.map((f) => (
                  <Badge key={f.code} tone={f.code === "PENDING_REVIEW" ? "neutral" : "warning"}>
                    {f.message}
                  </Badge>
                ))}
              </div>
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

export default async function ReconciliationPage({
  searchParams,
}: PageProps<"/finance/ride-hailing/reconciliation">) {
  await requirePermission("revenue:read");
  const sp = await searchParams;
  const filters = {
    date_from: spDate(sp, "date_from") ?? cairoToday(-30),
    date_to: spDate(sp, "date_to") ?? cairoToday(),
    driver_id: spUuid(sp, "driver_id"),
    vehicle_id: spUuid(sp, "vehicle_id"),
  };
  const [data, fleet] = await Promise.all([
    api.get<Reconciliation>("/ride-hailing/reconciliation", filters),
    fleetOptions(),
  ]);
  return (
    <>
      <PageHeader
        title="مطابقة النقل الذكي مع التشغيل"
        description="مقارنة كشوف المنصات بالورديات ووقت التشغيل والمسافة المسجلة. الملاحظات للمراجعة وليست اتهامًا."
        breadcrumb={<Link href="/finance/ride-hailing">النقل الذكي</Link>}
      />
      <Card className="mb-6">
        <FilterBar
          basePath="/finance/ride-hailing/reconciliation"
          values={filters}
          fields={[
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
            { type: "select", name: "driver_id", label: "السائق", options: fleet.drivers },
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
          ]}
        />
        <CardHeader title="الكشوف وما يقابلها من تشغيل" />
        {data.rows.length === 0 ? (
          <EmptyState title="لا توجد كشوف في الفترة" />
        ) : (
          <Rows rows={data.rows} withStatement />
        )}
      </Card>
      <Card>
        <CardHeader
          title="تشغيل نقل ذكي بدون كشف"
          description="أيام بها تشغيل نقل ذكي مسجل ولا يغطيها كشف منصة"
        />
        {data.uncovered.length === 0 ? (
          <EmptyState title="كل أيام التشغيل مغطاة بكشوف" />
        ) : (
          <Rows rows={data.uncovered} withStatement={false} />
        )}
      </Card>
    </>
  );
}
