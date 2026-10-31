import type { Metadata } from "next";
import Link from "next/link";
import { createSettlementAction } from "@/app/(app)/finance/actions";
import { FilterBar } from "@/components/finance/filters";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { SettlementStatusBadge } from "@/components/finance/review";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { options, SETTLEMENT_STATUS_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { Settlement } from "@/lib/finance-types";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { spEnum, spPage, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "تسويات السائقين" };

const STATUSES = ["DRAFT", "FINALIZED", "VOIDED"] as const;

export default async function SettlementsPage({ searchParams }: PageProps<"/finance/settlements">) {
  const me = await requirePermission("settlements:read");
  const sp = await searchParams;
  const filters = {
    driver_id: spUuid(sp, "driver_id"),
    status: spEnum(sp, "status", STATUSES),
  };
  const page = spPage(sp);
  const [data, fleet] = await Promise.all([
    api.get<Page<Settlement>>("/settlements", { ...filters, page, page_size: 25 }),
    fleetOptions(),
  ]);
  return (
    <>
      <PageHeader
        title="تسويات السائقين"
        description="حساب المستحقات حسب خطة التعويض السارية؛ التسوية النهائية لا تتغير بتغيير الخطة لاحقًا"
      />
      {can(me, "settlements:write") ? (
        <Card className="mb-6">
          <CardHeader
            title="تسوية جديدة"
            description="تُحسب كمسودة أولًا، ويمكن مراجعتها قبل الاعتماد"
          />
          <CardBody>
            <ActionForm action={createSettlementAction} submitLabel="حساب المسودة" variant="accent">
              <div className="grid gap-4 sm:grid-cols-3">
                <SelectField
                  name="driver_id"
                  label="السائق"
                  options={fleet.drivers}
                  placeholder="اختر السائق"
                  required
                />
                <TextField name="period_start" label="من" type="date" required />
                <TextField name="period_end" label="إلى" type="date" required />
              </div>
            </ActionForm>
          </CardBody>
        </Card>
      ) : null}
      <Card>
        <FilterBar
          basePath="/finance/settlements"
          values={filters}
          fields={[
            { type: "select", name: "driver_id", label: "السائق", options: fleet.drivers },
            {
              type: "select",
              name: "status",
              label: "الحالة",
              options: options(SETTLEMENT_STATUS_LABELS),
            },
          ]}
        />
        {data.items.length === 0 ? (
          <EmptyState title="لا توجد تسويات" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>السائق</TH>
                <TH>الفترة</TH>
                <TH>المستحقات</TH>
                <TH>الحالة</TH>
                <TH>الاعتماد</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((s) => (
                <TR key={s.id}>
                  <TD>
                    <Link
                      href={`/finance/settlements/${s.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {s.driver.name}
                    </Link>
                  </TD>
                  <TD>
                    {formatDate(s.period_start)} — {formatDate(s.period_end)}
                  </TD>
                  <TD className="ltr-nums font-medium">{formatMoney(s.earnings_amount)}</TD>
                  <TD>
                    <SettlementStatusBadge status={s.status} />
                  </TD>
                  <TD className="text-ink-muted">
                    {s.finalized_at
                      ? `${formatDateTime(s.finalized_at)} · ${s.finalized_by?.full_name ?? ""}`
                      : "—"}
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
          basePath="/finance/settlements"
          params={filters}
        />
      </Card>
    </>
  );
}
