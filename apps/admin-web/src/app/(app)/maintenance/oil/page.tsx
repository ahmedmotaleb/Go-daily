import type { Metadata } from "next";
import Link from "next/link";
import { FilterBar, Stat } from "@/components/finance/filters";
import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { UNIT_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import type { OilReconciliation } from "@/lib/maintenance-types";
import { spDate, spUuid } from "@/lib/search";

export const metadata: Metadata = { title: "مطابقة الزيوت والخدمات" };

const TONE: Record<string, Tone> = {
  NOT_LINKED: "warning",
  OVER_USED: "danger",
  PARTLY_USED: "info",
  USED: "success",
  NO_QUANTITY: "warning",
  NO_PURCHASE: "warning",
  OK: "success",
  NO_SERVICE: "warning",
  MATCHED: "success",
};

function Status({ status, label }: { status: string; label: string }) {
  return <Badge tone={TONE[status] ?? "neutral"}>{label}</Badge>;
}

function unit(u: string) {
  return UNIT_LABELS[u as keyof typeof UNIT_LABELS] ?? u;
}

export default async function OilReconciliationPage({
  searchParams,
}: PageProps<"/maintenance/oil">) {
  await requirePermission("maintenance:read");
  const sp = await searchParams;
  const filters = {
    vehicle_id: spUuid(sp, "vehicle_id"),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const [data, fleet] = await Promise.all([
    api.get<OilReconciliation>("/maintenance/oil-reconciliation", filters),
    fleetOptions(),
  ]);
  const unlinked = data.purchases.filter((p) => p.status === "NOT_LINKED").length;
  const orphan = data.expenses.filter((e) => e.status === "NO_SERVICE").length;
  return (
    <>
      <PageHeader
        title="مطابقة الزيوت والخدمات"
        description="شراء الزيت ليس تغييره: المشتريات، والخدمات التي استخدمتها، ومصروفات تغيير الزيت من التقفيل. ما يظهر هنا للمتابعة وليس حكمًا"
        breadcrumb={<Link href="/maintenance">الصيانة</Link>}
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="الفترة"
          value={`${formatDate(data.date_from)} — ${formatDate(data.date_to)}`}
        />
        <Stat
          label="للمتابعة"
          value={formatNumber(data.to_check)}
          tone={data.to_check ? "warning" : undefined}
        />
        <Stat label="مشتريات غير مرتبطة بخدمة" value={formatNumber(unlinked)} />
        <Stat label="مصروفات تغيير زيت بدون سجل صيانة" value={formatNumber(orphan)} />
      </div>
      <Card className="mb-6">
        <FilterBar
          basePath="/maintenance/oil"
          values={filters}
          fields={[
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
          ]}
        />
      </Card>
      <Card className="mb-6">
        <CardHeader
          title="مشتريات الزيوت والمستهلكات"
          description="الكمية المستخدمة من سجلات الصيانة المرتبطة بكل شراء"
        />
        {data.purchases.length === 0 ? (
          <EmptyState title="لا توجد مشتريات في الفترة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>الصنف</TH>
                <TH>المشترى</TH>
                <TH>المستخدم</TH>
                <TH>المبلغ</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.purchases.map((p) => (
                <TR key={p.id}>
                  <TD>
                    <Link
                      href={`/finance/fuel/${p.id}`}
                      className="font-semibold text-primary hover:underline"
                    >
                      {formatDate(p.day)}
                    </Link>
                  </TD>
                  <TD className="ltr-nums">{p.vehicle}</TD>
                  <TD>{p.item}</TD>
                  <TD className="ltr-nums">
                    {formatNumber(p.quantity)} {unit(p.unit)}
                  </TD>
                  <TD className="ltr-nums">
                    {p.used === null ? "—" : `${formatNumber(p.used)} ${unit(p.unit)}`}
                  </TD>
                  <TD className="ltr-nums">{formatMoney(p.total_amount)}</TD>
                  <TD>
                    <Status status={p.status} label={p.label} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Card className="mb-6">
        <CardHeader title="خدمات تستخدم مستهلكًا" description="مثل تغيير زيت الموتور" />
        {data.services.length === 0 ? (
          <EmptyState title="لا توجد خدمات في الفترة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>الخدمة</TH>
                <TH>الكمية</TH>
                <TH>الشراء</TH>
                <TH>الخدمة القادمة</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.services.map((s) => (
                <TR key={s.id}>
                  <TD>
                    <Link
                      href={`/maintenance/records/${s.id}`}
                      className="font-semibold text-primary hover:underline"
                    >
                      {formatDate(s.day)}
                    </Link>
                  </TD>
                  <TD className="ltr-nums">{s.vehicle}</TD>
                  <TD>{s.service}</TD>
                  <TD className="ltr-nums">
                    {formatNumber(s.quantity)}
                    {s.spec ? <span className="block text-xs text-ink-muted">{s.spec}</span> : null}
                  </TD>
                  <TD>
                    {s.purchase_id ? (
                      <Link
                        href={`/finance/fuel/${s.purchase_id}`}
                        className="text-primary hover:underline"
                      >
                        مرتبط
                      </Link>
                    ) : Number(s.parts_cost) > 0 ? (
                      `قطع ${formatMoney(s.parts_cost)}`
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD className="ltr-nums">
                    {s.next_due_km ? `${formatNumber(s.next_due_km)} كم` : ""}
                    {s.next_due_on ? (
                      <span className="block text-xs text-ink-muted">
                        {formatDate(s.next_due_on)}
                      </span>
                    ) : null}
                    {!s.next_due_km && !s.next_due_on ? "—" : null}
                  </TD>
                  <TD>
                    <Status status={s.status} label={s.label} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Card>
        <CardHeader
          title="مصروفات تغيير الزيت من التقفيل"
          description="تُطابق مع سجل صيانة للمركبة نفسها خلال 3 أيام"
        />
        {data.expenses.length === 0 ? (
          <EmptyState title="لا توجد مصروفات تغيير زيت في الفترة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>المبلغ</TH>
                <TH>سجل الصيانة</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.expenses.map((e) => (
                <TR key={e.id}>
                  <TD>
                    <Link
                      href={`/finance/expenses/${e.id}`}
                      className="font-semibold text-primary hover:underline"
                    >
                      {formatDate(e.day)}
                    </Link>
                  </TD>
                  <TD className="ltr-nums">{e.vehicle}</TD>
                  <TD className="ltr-nums">{formatMoney(e.amount)}</TD>
                  <TD>
                    {e.service_id ? (
                      <Link
                        href={`/maintenance/records/${e.service_id}`}
                        className="text-primary hover:underline"
                      >
                        عرض
                      </Link>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD>
                    <Status status={e.status} label={e.label} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
