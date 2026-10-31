import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { FilterBar, Stat } from "@/components/finance/filters";
import { RecordStatusBadge } from "@/components/finance/review";
import { DueTable } from "@/components/maintenance/due";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { options, RECORD_STATUS_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { DueItem, MaintenanceRecord, MaintenanceType } from "@/lib/maintenance-types";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { spDate, spEnum, spPage, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "الصيانة" };

const STATUSES = ["SUBMITTED", "APPROVED", "REJECTED", "VOIDED"] as const;

export default async function MaintenancePage({ searchParams }: PageProps<"/maintenance">) {
  const me = await requirePermission("maintenance:read");
  const sp = await searchParams;
  const filters = {
    vehicle_id: spUuid(sp, "vehicle_id"),
    type_id: spUuid(sp, "type_id"),
    status: spEnum(sp, "status", STATUSES),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const page = spPage(sp);
  const [due, records, types, fleet] = await Promise.all([
    api.get<DueItem[]>("/maintenance/due"),
    api.get<Page<MaintenanceRecord>>("/maintenance/records", { ...filters, page, page_size: 25 }),
    api.get<MaintenanceType[]>("/maintenance/types", { include_inactive: true }),
    fleetOptions(),
  ]);
  const overdue = due.filter((d) => d.state === "OVERDUE").length;
  const soon = due.filter((d) => d.state === "DUE_SOON").length;
  const attention = due.filter((d) => d.state === "OVERDUE" || d.state === "DUE_SOON");

  return (
    <>
      <PageHeader
        title="الصيانة"
        description="جداول الصيانة حسب الكيلومترات أو المدة، وسجلات الصيانة المنفذة وتكاليفها"
        actions={
          can(me, "maintenance:write") ? (
            <ButtonLink href="/maintenance/records/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              تسجيل صيانة
            </ButtonLink>
          ) : null
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Stat
          label="صيانة متأخرة"
          value={formatNumber(overdue)}
          tone={overdue ? "danger" : undefined}
        />
        <Stat label="صيانة قريبة" value={formatNumber(soon)} tone={soon ? "warning" : undefined} />
        <Stat label="جداول مفعلة" value={formatNumber(due.length)} hint="تُضبط من صفحة كل مركبة" />
      </div>
      <Card className="mb-6">
        <CardHeader
          title="تحتاج متابعة"
          description="المتأخرة والقريبة فقط؛ كل الجداول في صفحات المركبات"
        />
        {attention.length === 0 ? (
          <EmptyState title="لا توجد صيانة متأخرة أو قريبة" />
        ) : (
          <DueTable rows={attention} />
        )}
      </Card>
      <Card>
        <CardHeader title="سجلات الصيانة" />
        <FilterBar
          basePath="/maintenance"
          values={filters}
          fields={[
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            {
              type: "select",
              name: "type_id",
              label: "النوع",
              options: types.map((t) => ({ value: t.id, label: t.name_ar })),
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
        {records.items.length === 0 ? (
          <EmptyState title="لا توجد سجلات صيانة مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>النوع</TH>
                <TH>العداد</TH>
                <TH>الورشة</TH>
                <TH>التكلفة</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {records.items.map((r) => (
                <TR key={r.id}>
                  <TD>
                    <Link
                      href={`/maintenance/records/${r.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {formatDate(r.performed_on)}
                    </Link>
                  </TD>
                  <TD className="ltr-nums">{r.vehicle.name}</TD>
                  <TD>{r.type.name_ar}</TD>
                  <TD className="ltr-nums">
                    {r.odometer_km === null ? "—" : formatNumber(r.odometer_km)}
                  </TD>
                  <TD>{r.vendor ?? "—"}</TD>
                  <TD className="ltr-nums font-medium">{formatMoney(r.total_cost)}</TD>
                  <TD>
                    <RecordStatusBadge status={r.status} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
        <Pagination
          page={records.page}
          pageSize={records.page_size}
          total={records.total}
          basePath="/maintenance"
          params={filters}
        />
      </Card>
    </>
  );
}
