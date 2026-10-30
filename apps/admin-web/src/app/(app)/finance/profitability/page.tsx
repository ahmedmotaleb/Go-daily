import type { Metadata } from "next";
import { FilterBar, Stat } from "@/components/finance/filters";
import { Alert } from "@/components/ui/alert";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { EXPENSE_GROUP_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { FleetPnl, VehiclePnl } from "@/lib/finance-types";
import { formatMoney, formatNumber } from "@/lib/format";
import { firstOfMonth, cairoToday, spDate, spUuid } from "@/lib/search";

export const metadata: Metadata = { title: "ربحية المركبات" };

function Money({ value, strong }: { value: string | null; strong?: boolean }) {
  const negative = value !== null && Number(value) < 0;
  return (
    <span className={`ltr-nums ${strong ? "font-bold" : ""} ${negative ? "text-danger" : ""}`}>
      {formatMoney(value)}
    </span>
  );
}

function VehicleDetail({ v }: { v: VehiclePnl }) {
  return (
    <Card>
      <CardHeader
        title={v.vehicle.name}
        description={`${formatNumber(v.shifts_count)} وردية · ${formatNumber(v.odometer_km)} كم بالعداد · ${formatNumber(v.gps_km)} كم GPS`}
        actions={<Money value={v.net_operating_profit} strong />}
      />
      <CardBody className="space-y-4">
        {v.warnings.filter((w) => w.code !== "MAINTENANCE_FROM_EXPENSES").length ? (
          <Alert tone="warning">
            <p className="mb-1 font-semibold">بيانات غير مكتملة — الأرقام كما سُجلت دون تقدير:</p>
            <ul className="list-inside list-disc space-y-0.5 text-sm">
              {v.warnings
                .filter((w) => w.code !== "MAINTENANCE_FROM_EXPENSES")
                .map((w) => (
                  <li key={w.code}>
                    {w.message}
                    {w.count !== null ? ` (${formatNumber(w.count)})` : ""}
                  </li>
                ))}
            </ul>
          </Alert>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between">
              <dt>إجمالي الإيراد</dt>
              <dd>
                <Money value={v.gross_revenue} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>عمولات المنصات</dt>
              <dd>
                <Money value={v.platform_fees} />
              </dd>
            </div>
            {Object.entries(v.fuel_by_type).map(([code, amount]) => (
              <div key={code} className="flex justify-between text-ink-muted">
                <dt>· {code}</dt>
                <dd>
                  <Money value={amount} />
                </dd>
              </div>
            ))}
            <div className="flex justify-between">
              <dt>وقود</dt>
              <dd>
                <Money value={v.fuel_cost} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>زيوت ومستهلكات</dt>
              <dd>
                <Money value={v.consumables_cost} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>صيانة</dt>
              <dd>
                <Money value={v.maintenance_cost} />
              </dd>
            </div>
            {Object.entries(v.expenses_by_group)
              .filter(([g]) => g !== "MAINTENANCE")
              .map(([group, amount]) => (
                <div key={group} className="flex justify-between">
                  <dt>
                    مصروفات{" "}
                    {EXPENSE_GROUP_LABELS[group as keyof typeof EXPENSE_GROUP_LABELS] ?? group}
                  </dt>
                  <dd>
                    <Money value={amount} />
                  </dd>
                </div>
              ))}
            <div className="flex justify-between border-t border-line pt-1 font-semibold">
              <dt>تكلفة تشغيل مباشرة</dt>
              <dd>
                <Money value={v.direct_operating_cost} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>تكلفة السائقين</dt>
              <dd>
                <Money value={v.driver_cost} />
              </dd>
            </div>
            <div className="flex justify-between border-t border-line pt-1 font-bold">
              <dt>صافي ربح التشغيل</dt>
              <dd>
                <Money value={v.net_operating_profit} strong />
              </dd>
            </div>
          </dl>
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <Stat label="تكلفة/كم" value={formatMoney(v.cost_per_km)} />
              <Stat label="إيراد/كم" value={formatMoney(v.revenue_per_km)} />
              <Stat label="ربح/وردية" value={formatMoney(v.profit_per_shift)} />
            </div>
            {v.by_operation_type.length ? (
              <Table>
                <THead>
                  <tr>
                    <TH>نوع التشغيل</TH>
                    <TH>إيراد</TH>
                    <TH>تكلفة موزعة</TH>
                    <TH>ربح</TH>
                  </tr>
                </THead>
                <tbody>
                  {v.by_operation_type.map((row) => (
                    <TR key={row.operation_type?.id ?? "none"}>
                      <TD>{row.operation_type?.name ?? "غير محدد"}</TD>
                      <TD>
                        <Money value={row.revenue} />
                      </TD>
                      <TD>
                        <Money value={row.allocated_cost} />
                      </TD>
                      <TD>
                        <Money value={row.profit} />
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            ) : null}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

export default async function ProfitabilityPage({
  searchParams,
}: PageProps<"/finance/profitability">) {
  await requirePermission("profitability:read");
  const sp = await searchParams;
  const filters = {
    date_from: spDate(sp, "date_from") ?? firstOfMonth(),
    date_to: spDate(sp, "date_to") ?? cairoToday(),
    vehicle_id: spUuid(sp, "vehicle_id"),
  };
  const [data, fleet] = await Promise.all([
    api.get<FleetPnl>("/profitability/vehicles", filters),
    fleetOptions(),
  ]);
  const t = data.totals;
  return (
    <>
      <PageHeader
        title="ربحية المركبات"
        description="من السجلات المعتمدة فقط. التكاليف بدون فترة تُحسب بتاريخها، والعقود والتسويات توزع على أيام فترتها، وتكلفة السائق توزع حسب دقائق القيادة."
      />
      <Card className="mb-4">
        <FilterBar
          basePath="/finance/profitability"
          values={filters}
          fields={[
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
          ]}
        />
      </Card>
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="إجمالي الإيراد" value={formatMoney(t.gross_revenue)} />
        <Stat label="تكلفة تشغيل مباشرة" value={formatMoney(t.direct_operating_cost)} />
        <Stat label="تكلفة السائقين" value={formatMoney(t.driver_cost)} />
        <Stat
          label="صافي ربح التشغيل"
          value={formatMoney(t.net_operating_profit)}
          tone={Number(t.net_operating_profit) < 0 ? "danger" : "success"}
        />
        <Stat
          label="تكلفة سائقين غير موزعة"
          value={formatMoney(t.unallocated_driver_cost)}
          hint="مستحقات بلا ورديات مسجلة في الفترة"
        />
      </div>
      {data.vehicles.length === 0 ? (
        <Card>
          <EmptyState title="لا توجد مركبات أو نشاط في الفترة" />
        </Card>
      ) : (
        <>
          <Card className="mb-6">
            <Table>
              <THead>
                <tr>
                  <TH>المركبة</TH>
                  <TH>الإيراد</TH>
                  <TH>وقود</TH>
                  <TH>صيانة</TH>
                  <TH>مصروفات أخرى</TH>
                  <TH>سائقون</TH>
                  <TH>الصافي</TH>
                  <TH>تكلفة/كم</TH>
                  <TH>تنبيهات</TH>
                </tr>
              </THead>
              <tbody>
                {data.vehicles.map((v) => (
                  <TR key={v.vehicle.id}>
                    <TD>
                      <a
                        href={`#v-${v.vehicle.id}`}
                        className="ltr-nums font-semibold text-forest-700 hover:underline"
                      >
                        {v.vehicle.name}
                      </a>
                    </TD>
                    <TD>
                      <Money value={v.gross_revenue} />
                    </TD>
                    <TD>
                      <Money value={v.fuel_cost} />
                    </TD>
                    <TD>
                      <Money value={v.maintenance_cost} />
                    </TD>
                    <TD>
                      <Money value={v.other_expenses} />
                    </TD>
                    <TD>
                      <Money value={v.driver_cost} />
                    </TD>
                    <TD>
                      <Money value={v.net_operating_profit} strong />
                    </TD>
                    <TD>
                      <Money value={v.cost_per_km} />
                    </TD>
                    <TD className="ltr-nums">
                      {formatNumber(
                        v.warnings.filter((w) => w.code !== "MAINTENANCE_FROM_EXPENSES").length,
                      )}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </Card>
          <div className="space-y-6">
            {data.vehicles.map((v) => (
              <section key={v.vehicle.id} id={`v-${v.vehicle.id}`}>
                <VehicleDetail v={v} />
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}
