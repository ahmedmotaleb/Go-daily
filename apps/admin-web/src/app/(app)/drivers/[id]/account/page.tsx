import type { Metadata } from "next";
import Link from "next/link";
import { addLedgerEntryAction, voidLedgerEntryAction } from "@/app/(app)/finance/actions";
import { FilterBar, Stat } from "@/components/finance/filters";
import { LedgerForm } from "@/components/finance/ledger-form";
import { ActionForm } from "@/components/forms/action-form";
import { TextField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { LEDGER_TYPE_LABELS } from "@/lib/finance-labels";
import type { DriverStatement, LedgerEntry } from "@/lib/finance-types";
import { formatDate, formatMoney } from "@/lib/format";
import { cairoToday, spDate } from "@/lib/search";

export const metadata: Metadata = { title: "حساب السائق" };

const SOURCE_LINKS: Partial<Record<LedgerEntry["source_type"], string>> = {
  FUEL: "/finance/fuel",
  EXPENSE: "/finance/expenses",
  SETTLEMENT: "/finance/settlements",
};

/** Sign handled on the decimal string itself: money is never float arithmetic. */
const magnitude = (value: string) => value.replace(/^-/, "");

function balanceLabel(value: string) {
  const n = Number(value);
  if (n > 0) return `للسائق ${formatMoney(value)}`;
  if (n < 0) return `على السائق ${formatMoney(magnitude(value))}`;
  return "متوازن";
}

export default async function DriverAccountPage({
  params,
  searchParams,
}: PageProps<"/drivers/[id]/account">) {
  const me = await requirePermission("settlements:read");
  const { id } = await params;
  const sp = await searchParams;
  const range = {
    date_from: spDate(sp, "date_from") ?? cairoToday(-30),
    date_to: spDate(sp, "date_to") ?? cairoToday(),
  };
  const st = await api.get<DriverStatement>(`/drivers/${id}/statement`, range);
  const canVoid = can(me, "settlements:finalize");

  return (
    <>
      <PageHeader
        title={`حساب ${st.driver.name}`}
        description="الرصيد = ما تستحقه للسائق (موجب) أو ما في عهدته للشركة (سالب)"
        breadcrumb={<Link href={`/drivers/${id}`}>{st.driver.name}</Link>}
      />
      <Notice code={sp.notice} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="الرصيد الافتتاحي" value={balanceLabel(st.opening_balance)} />
        <Stat
          label="المستحقات"
          value={formatMoney(st.earned)}
          hint={`مكافآت: ${formatMoney(st.bonuses)}`}
        />
        <Stat
          label="تحصيلات لدى السائق"
          value={formatMoney(magnitude(st.cash_collected))}
          hint={`سُلّم: ${formatMoney(st.cash_handed_over)}`}
        />
        <Stat
          label="الرصيد الختامي"
          value={balanceLabel(st.closing_balance)}
          tone={Number(st.closing_balance) < 0 ? "warning" : undefined}
        />
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="تعويض مصروفات" value={formatMoney(st.reimbursements)} />
        <Stat label="سلف" value={formatMoney(magnitude(st.advances))} />
        <Stat label="خصومات" value={formatMoney(magnitude(st.deductions))} />
        <Stat label="مصروف للسائق" value={formatMoney(magnitude(st.paid))} />
        <Stat label="تسويات" value={formatMoney(st.adjustments)} />
      </div>
      <Card>
        <FilterBar
          basePath={`/drivers/${id}/account`}
          values={range}
          fields={[
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
          ]}
        />
        {st.entries.length === 0 ? (
          <EmptyState title="لا توجد قيود في الفترة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>النوع</TH>
                <TH>البيان</TH>
                <TH>المبلغ</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {st.entries.map((e) => {
                const link = SOURCE_LINKS[e.source_type];
                return (
                  <TR key={e.id} className={e.voided_at ? "opacity-60" : undefined}>
                    <TD>{formatDate(e.occurred_on)}</TD>
                    <TD>{LEDGER_TYPE_LABELS[e.entry_type]}</TD>
                    <TD>
                      {link && e.source_id ? (
                        <Link href={`${link}/${e.source_id}`} className="hover:underline">
                          {e.description}
                        </Link>
                      ) : (
                        e.description
                      )}
                      {e.reason ? (
                        <span className="block text-xs text-ink-muted">{e.reason}</span>
                      ) : null}
                    </TD>
                    <TD
                      className={`ltr-nums font-medium ${Number(e.amount) < 0 ? "text-danger" : "text-success"}`}
                    >
                      {formatMoney(e.amount)}
                    </TD>
                    <TD>
                      {e.voided_at ? (
                        <Badge>ملغي: {e.void_reason}</Badge>
                      ) : canVoid && e.source_type === "MANUAL" ? (
                        <details>
                          <summary className="cursor-pointer text-xs text-danger">إلغاء</summary>
                          <ActionForm
                            action={voidLedgerEntryAction.bind(null, e.id, id)}
                            submitLabel="إلغاء القيد"
                            variant="danger"
                            className="mt-2 w-64"
                          >
                            <TextField name="reason" label="السبب" required />
                          </ActionForm>
                        </details>
                      ) : (
                        <Badge tone="success">ساري</Badge>
                      )}
                    </TD>
                  </TR>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
      {can(me, "settlements:write") ? (
        <Card className="mt-6">
          <CardHeader
            title="قيد يدوي"
            description="المستحقات تُرحّل من التسويات، والتحصيلات والتعويضات من سجلاتها تلقائيًا"
          />
          <CardBody>
            <LedgerForm action={addLedgerEntryAction.bind(null, id)} />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
