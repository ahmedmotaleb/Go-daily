import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { FilterBar, Stat } from "@/components/finance/filters";
import { RecordStatusBadge } from "@/components/finance/review";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { options, RECORD_STATUS_LABELS, REVENUE_KIND_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { RevenueEntry, RevenueSummary } from "@/lib/finance-types";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { spDate, spEnum, spPage, spString, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "الإيرادات والتحصيل" };

const STATUSES = ["SUBMITTED", "APPROVED", "REJECTED", "VOIDED"] as const;
const KINDS = [
  "FIXED_ROUTE_COLLECTION",
  "CONTRACT_SERVICE",
  "PRIVATE_TRIP",
  "RIDE_HAILING",
  "OTHER",
] as const;

export default async function RevenuePage({ searchParams }: PageProps<"/finance/revenue">) {
  const me = await requirePermission("revenue:read");
  const sp = await searchParams;
  const filters = {
    vehicle_id: spUuid(sp, "vehicle_id"),
    driver_id: spUuid(sp, "driver_id"),
    kind: spEnum(sp, "kind", KINDS),
    status: spEnum(sp, "status", STATUSES),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const outstanding = spString(sp, "outstanding_only") === "true";
  const page = spPage(sp);
  const [data, summary, fleet] = await Promise.all([
    api.get<Page<RevenueEntry>>("/revenue", {
      ...filters,
      outstanding_only: outstanding || undefined,
      page,
      page_size: 25,
    }),
    api.get<RevenueSummary>("/revenue/summary", filters),
    fleetOptions(),
  ]);

  return (
    <>
      <PageHeader
        title="الإيرادات والتحصيل"
        description="سجل واحد لكل إيراد مستحق، والمبالغ المستلمة نقدًا أو إلكترونيًا مسجلة عليه"
        actions={
          can(me, "revenue:write") ? (
            <ButtonLink href="/finance/revenue/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              تسجيل إيراد
            </ButtonLink>
          ) : null
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="الإيراد المعتمد" value={formatMoney(summary.gross_amount)} />
        <Stat label="عمولات مخصومة" value={formatMoney(summary.fees_withheld)} />
        <Stat label="مستلم نقدًا" value={formatMoney(summary.received_cash)} />
        <Stat label="مستلم إلكترونيًا" value={formatMoney(summary.received_electronic)} />
        <Stat
          label="متبقي غير محصل"
          value={formatMoney(summary.outstanding_amount)}
          tone={Number(summary.outstanding_amount) > 0 ? "warning" : undefined}
          hint={
            summary.pending_count
              ? `${formatNumber(summary.pending_count)} بانتظار المراجعة`
              : undefined
          }
        />
      </div>
      <Card>
        <FilterBar
          basePath="/finance/revenue"
          values={{ ...filters, outstanding_only: outstanding ? "true" : undefined }}
          fields={[
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            { type: "select", name: "driver_id", label: "السائق", options: fleet.drivers },
            { type: "select", name: "kind", label: "النوع", options: options(REVENUE_KIND_LABELS) },
            {
              type: "select",
              name: "status",
              label: "الحالة",
              options: options(RECORD_STATUS_LABELS),
            },
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
            { type: "checkbox", name: "outstanding_only", label: "غير المحصل فقط" },
          ]}
        />
        {data.items.length === 0 ? (
          <EmptyState title="لا توجد إيرادات مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>النوع</TH>
                <TH>المركبة / السائق</TH>
                <TH>المستحق</TH>
                <TH>المستلم</TH>
                <TH>المتبقي</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((r) => (
                <TR key={r.id}>
                  <TD>
                    <Link
                      href={`/finance/revenue/${r.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {formatDate(r.occurred_on)}
                    </Link>
                  </TD>
                  <TD>
                    {REVENUE_KIND_LABELS[r.kind]}
                    {r.customer_name ? (
                      <span className="block text-xs text-ink-muted">{r.customer_name}</span>
                    ) : null}
                  </TD>
                  <TD>
                    <span className="ltr-nums">{r.vehicle.name}</span>
                    {r.driver ? (
                      <span className="block text-xs text-ink-muted">{r.driver.name}</span>
                    ) : null}
                  </TD>
                  <TD className="ltr-nums font-medium">{formatMoney(r.amount)}</TD>
                  <TD className="ltr-nums">{formatMoney(r.received_amount)}</TD>
                  <TD className="ltr-nums">
                    {Number(r.outstanding_amount) > 0 ? (
                      <span className="text-warning">{formatMoney(r.outstanding_amount)}</span>
                    ) : (
                      formatMoney(r.outstanding_amount)
                    )}
                  </TD>
                  <TD>
                    <RecordStatusBadge status={r.status} />
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
          basePath="/finance/revenue"
          params={{ ...filters, outstanding_only: outstanding ? "true" : undefined }}
        />
      </Card>
    </>
  );
}
