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
  EXPENSE_GROUP_LABELS,
  options,
  PAID_BY_LABELS,
  RECORD_STATUS_LABELS,
} from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { Expense, ExpenseCategory, ExpenseSummary } from "@/lib/finance-types";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import { spDate, spEnum, spPage, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "المصروفات" };

const STATUSES = ["SUBMITTED", "APPROVED", "REJECTED", "VOIDED"] as const;
const GROUPS = ["OPERATING", "MAINTENANCE", "FINES", "OTHER"] as const;

export default async function ExpensesPage({ searchParams }: PageProps<"/finance/expenses">) {
  const me = await requirePermission("expenses:read");
  const sp = await searchParams;
  const filters = {
    vehicle_id: spUuid(sp, "vehicle_id"),
    category_id: spUuid(sp, "category_id"),
    group: spEnum(sp, "group", GROUPS),
    status: spEnum(sp, "status", STATUSES),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const page = spPage(sp);
  const [data, summary, categories, fleet] = await Promise.all([
    api.get<Page<Expense>>("/expenses", { ...filters, page, page_size: 25 }),
    api.get<ExpenseSummary>("/expenses/summary", filters),
    api.get<ExpenseCategory[]>("/expense-categories", { include_inactive: true }),
    fleetOptions(),
  ]);

  return (
    <>
      <PageHeader
        title="المصروفات"
        description="رسوم الطرق والانتظار والغسيل والإصلاحات وغيرها، بتصنيفات قابلة للإعداد"
        actions={
          can(me, "expenses:write") ? (
            <ButtonLink href="/finance/expenses/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              تسجيل مصروف
            </ButtonLink>
          ) : null
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Stat label="إجمالي المعتمد" value={formatMoney(summary.total_amount)} />
        <Stat
          label="بانتظار المراجعة"
          value={formatNumber(summary.pending_count)}
          tone={summary.pending_count ? "warning" : undefined}
          hint="غير محسوبة في الإجماليات"
        />
        <div className="rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3 text-sm">
          <p className="text-xs text-ink-muted">حسب التصنيف (معتمد)</p>
          {summary.by_category.length === 0 ? (
            <p className="mt-1 text-ink-muted">—</p>
          ) : (
            <ul className="mt-1 space-y-0.5">
              {summary.by_category.map((row) => (
                <li key={row.category.id} className="flex justify-between gap-2">
                  <span>{row.category.name_ar}</span>
                  <span className="ltr-nums">{formatMoney(row.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <Card>
        <FilterBar
          basePath="/finance/expenses"
          values={filters}
          fields={[
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            {
              type: "select",
              name: "category_id",
              label: "التصنيف",
              options: categories.map((c) => ({ value: c.id, label: c.name_ar })),
            },
            {
              type: "select",
              name: "group",
              label: "المجموعة",
              options: options(EXPENSE_GROUP_LABELS),
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
          <EmptyState title="لا توجد مصروفات مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>التصنيف</TH>
                <TH>المورد</TH>
                <TH>المبلغ</TH>
                <TH>الدافع</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((e) => (
                <TR key={e.id}>
                  <TD>
                    <Link
                      href={`/finance/expenses/${e.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {formatDateTime(e.occurred_at)}
                    </Link>
                  </TD>
                  <TD className="ltr-nums">{e.vehicle.name}</TD>
                  <TD>
                    {e.category.name_ar}
                    <span className="block text-xs text-ink-muted">
                      {EXPENSE_GROUP_LABELS[e.category.pnl_group]}
                    </span>
                  </TD>
                  <TD>{e.vendor ?? "—"}</TD>
                  <TD className="ltr-nums font-medium">{formatMoney(e.amount)}</TD>
                  <TD>{PAID_BY_LABELS[e.paid_by]}</TD>
                  <TD>
                    <RecordStatusBadge status={e.status} />
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
          basePath="/finance/expenses"
          params={filters}
        />
      </Card>
    </>
  );
}
