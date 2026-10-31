import { Plus, Scale } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { FilterBar } from "@/components/finance/filters";
import { RecordStatusBadge } from "@/components/finance/review";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { options, RECORD_STATUS_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { Platform, Statement } from "@/lib/finance-types";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { spDate, spEnum, spPage, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "النقل الذكي" };

const STATUSES = ["SUBMITTED", "APPROVED", "REJECTED", "VOIDED"] as const;

export default async function StatementsPage({ searchParams }: PageProps<"/finance/ride-hailing">) {
  const me = await requirePermission("revenue:read");
  const sp = await searchParams;
  const filters = {
    platform_id: spUuid(sp, "platform_id"),
    driver_id: spUuid(sp, "driver_id"),
    vehicle_id: spUuid(sp, "vehicle_id"),
    status: spEnum(sp, "status", STATUSES),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const page = spPage(sp);
  const [data, platforms, fleet] = await Promise.all([
    api.get<Page<Statement>>("/ride-hailing/statements", { ...filters, page, page_size: 25 }),
    api.get<Platform[]>("/ride-hailing/platforms", { include_inactive: true }),
    fleetOptions(),
  ]);

  return (
    <>
      <PageHeader
        title="النقل الذكي"
        description="كشوف أرباح المنصات تُدخل يدويًا من كشف المنصة؛ لا يتم سحب بيانات من أي منصة"
        actions={
          <div className="flex flex-wrap gap-2">
            <ButtonLink href="/finance/ride-hailing/reconciliation" variant="secondary">
              <Scale className="size-4" aria-hidden="true" />
              المطابقة مع التشغيل
            </ButtonLink>
            {can(me, "revenue:write") ? (
              <ButtonLink href="/finance/ride-hailing/new" variant="accent">
                <Plus className="size-4" aria-hidden="true" />
                كشف جديد
              </ButtonLink>
            ) : null}
          </div>
        }
      />
      {platforms.length === 0 ? (
        <p className="mb-4 rounded-[var(--radius-card)] border border-dashed border-line bg-surface px-4 py-3 text-sm text-ink-muted">
          لا توجد منصات بعد. أضف المنصات من{" "}
          <Link href="/finance/settings" className="text-forest-700 hover:underline">
            إعدادات المالية
          </Link>
          .
        </p>
      ) : null}
      <Card>
        <FilterBar
          basePath="/finance/ride-hailing"
          values={filters}
          fields={[
            {
              type: "select",
              name: "platform_id",
              label: "المنصة",
              options: platforms.map((p) => ({ value: p.id, label: p.name })),
            },
            { type: "select", name: "driver_id", label: "السائق", options: fleet.drivers },
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            {
              type: "select",
              name: "status",
              label: "الحالة",
              options: options(RECORD_STATUS_LABELS),
            },
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
          ]}
        />
        {data.items.length === 0 ? (
          <EmptyState title="لا توجد كشوف مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>الفترة</TH>
                <TH>المنصة</TH>
                <TH>السائق / المركبة</TH>
                <TH>الرحلات</TH>
                <TH>إجمالي الدخل</TH>
                <TH>العمولة</TH>
                <TH>الصافي</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((s) => (
                <TR key={s.id}>
                  <TD>
                    <Link
                      href={`/finance/ride-hailing/${s.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {formatDate(s.period_start)} — {formatDate(s.period_end)}
                    </Link>
                  </TD>
                  <TD>{s.platform.name}</TD>
                  <TD>
                    {s.driver.name}
                    <span className="ltr-nums block text-xs text-ink-muted">{s.vehicle.name}</span>
                  </TD>
                  <TD className="ltr-nums">{formatNumber(s.trips_count)}</TD>
                  <TD className="ltr-nums">{formatMoney(s.income)}</TD>
                  <TD className="ltr-nums">{formatMoney(s.platform_fees)}</TD>
                  <TD className="ltr-nums font-medium">{formatMoney(s.net_earnings)}</TD>
                  <TD>
                    <RecordStatusBadge status={s.status} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
        <Pagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          basePath="/finance/ride-hailing"
          params={filters}
        />
      </Card>
    </>
  );
}
