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
import {
  FUEL_CATEGORY_LABELS,
  options,
  PAID_BY_LABELS,
  RECORD_STATUS_LABELS,
  UNIT_LABELS,
} from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { FuelSummary, FuelTx, FuelType } from "@/lib/finance-types";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import { spDate, spEnum, spPage, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "الوقود والزيوت" };

const STATUSES = ["SUBMITTED", "APPROVED", "REJECTED", "VOIDED"] as const;
const CATEGORIES = ["FUEL", "CONSUMABLE"] as const;

export default async function FuelPage({ searchParams }: PageProps<"/finance/fuel">) {
  const me = await requirePermission("fuel:read");
  const sp = await searchParams;
  const filters = {
    vehicle_id: spUuid(sp, "vehicle_id"),
    fuel_type_id: spUuid(sp, "fuel_type_id"),
    category: spEnum(sp, "category", CATEGORIES),
    status: spEnum(sp, "status", STATUSES),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const page = spPage(sp);
  const [data, summary, types, fleet] = await Promise.all([
    api.get<Page<FuelTx>>("/fuel", { ...filters, page, page_size: 25 }),
    api.get<FuelSummary>("/fuel/summary", filters),
    api.get<FuelType[]>("/fuel-types", { include_inactive: true }),
    fleetOptions(),
  ]);

  return (
    <>
      <PageHeader
        title="الوقود والزيوت"
        description="غاز طبيعي وبنزين وسولار وزيت موتور — كل تعبئة سجل مستقل، والزيت لا يدخل في كفاءة الوقود"
        actions={
          can(me, "fuel:write") ? (
            <ButtonLink href="/finance/fuel/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              تسجيل وقود
            </ButtonLink>
          ) : null
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="الوقود المعتمد" value={formatMoney(summary.fuel_amount)} />
        <Stat label="زيوت ومستهلكات معتمدة" value={formatMoney(summary.consumables_amount)} />
        <Stat
          label="بانتظار المراجعة"
          value={formatNumber(summary.pending_count)}
          tone={summary.pending_count ? "warning" : undefined}
          hint="غير محسوبة في الإجماليات"
        />
        <div className="rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3 text-sm">
          <p className="text-xs text-ink-muted">حسب النوع (معتمد)</p>
          {summary.by_type.length === 0 ? (
            <p className="mt-1 text-ink-muted">—</p>
          ) : (
            <ul className="mt-1 space-y-0.5">
              {summary.by_type.map((row) => (
                <li key={row.fuel_type.id} className="flex justify-between gap-2">
                  <span>{row.fuel_type.name_ar}</span>
                  <span className="ltr-nums">
                    {formatNumber(row.quantity)} {UNIT_LABELS[row.fuel_type.default_unit]} ·{" "}
                    {formatMoney(row.total_amount)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <Card>
        <FilterBar
          basePath="/finance/fuel"
          values={filters}
          fields={[
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            {
              type: "select",
              name: "fuel_type_id",
              label: "النوع",
              options: types.map((t) => ({ value: t.id, label: t.name_ar })),
            },
            {
              type: "select",
              name: "category",
              label: "الفئة",
              options: options(FUEL_CATEGORY_LABELS),
            },
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
          <EmptyState title="لا توجد سجلات مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>النوع</TH>
                <TH>الكمية</TH>
                <TH>سعر الوحدة</TH>
                <TH>الإجمالي</TH>
                <TH>الدافع</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((tx) => (
                <TR key={tx.id}>
                  <TD>
                    <Link
                      href={`/finance/fuel/${tx.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {formatDateTime(tx.occurred_at)}
                    </Link>
                  </TD>
                  <TD>
                    <span className="ltr-nums">{tx.vehicle.name}</span>
                    {tx.driver ? (
                      <span className="block text-xs text-ink-muted">{tx.driver.name}</span>
                    ) : null}
                  </TD>
                  <TD>{tx.fuel_type.name_ar}</TD>
                  <TD className="ltr-nums">
                    {formatNumber(tx.quantity)} {UNIT_LABELS[tx.unit]}
                  </TD>
                  <TD className="ltr-nums">{formatMoney(tx.effective_unit_price)}</TD>
                  <TD className="ltr-nums font-medium">{formatMoney(tx.total_amount)}</TD>
                  <TD>{PAID_BY_LABELS[tx.paid_by]}</TD>
                  <TD>
                    <RecordStatusBadge status={tx.status} />
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
          basePath="/finance/fuel"
          params={filters}
        />
      </Card>
    </>
  );
}
