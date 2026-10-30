import type { Metadata } from "next";
import Link from "next/link";
import { settlementAction } from "@/app/(app)/finance/actions";
import { DetailRow } from "@/components/finance/filters";
import { SettlementStatusBadge } from "@/components/finance/review";
import { ActionForm } from "@/components/forms/action-form";
import { TextareaField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Alert } from "@/components/ui/alert";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import type { Settlement } from "@/lib/finance-types";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "تسوية سائق" };

export default async function SettlementPage({
  params,
  searchParams,
}: PageProps<"/finance/settlements/[id]">) {
  const me = await requirePermission("settlements:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const s = await api.get<Settlement>(`/settlements/${id}`);
  const canFinalize = can(me, "settlements:finalize");
  const canWrite = can(me, "settlements:write");
  const draft = s.status === "DRAFT";

  return (
    <>
      <PageHeader
        title={`تسوية ${s.driver.name}`}
        description={`${formatDate(s.period_start)} — ${formatDate(s.period_end)}`}
        breadcrumb={<Link href="/finance/settlements">تسويات السائقين</Link>}
        actions={<SettlementStatusBadge status={s.status} />}
      />
      <Notice code={notice} />
      {s.details.warnings.length ? (
        <Alert tone="warning" className="mb-4">
          <ul className="list-inside list-disc space-y-1">
            {s.details.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="تفاصيل الحساب"
            description={`محسوبة في ${formatDateTime(s.details.computed_at)}${draft ? " — مسودة قابلة لإعادة الحساب" : ""}`}
          />
          <Table>
            <THead>
              <tr>
                <TH>طريقة التعويض</TH>
                <TH>الفترة</TH>
                <TH>الأساس</TH>
                <TH>المبلغ</TH>
              </tr>
            </THead>
            <tbody>
              {s.details.lines.length === 0 ? (
                <TR>
                  <TD colSpan={4} className="text-ink-muted">
                    لا توجد خطة تعويض سارية في الفترة
                  </TD>
                </TR>
              ) : (
                s.details.lines.map((line) => (
                  <TR key={`${line.plan_id}-${line.period_start}`}>
                    <TD>{line.label}</TD>
                    <TD>
                      {formatDate(line.period_start)} — {formatDate(line.period_end)}
                    </TD>
                    <TD className="text-ink-muted">{line.basis}</TD>
                    <TD className="ltr-nums font-medium">{formatMoney(line.amount)}</TD>
                  </TR>
                ))
              )}
            </tbody>
          </Table>
        </Card>
        <Card>
          <CardHeader title="الملخص" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="أيام العمل">{formatNumber(s.details.days_worked)}</DetailRow>
              <DetailRow label="الإيراد المؤهل">
                <span className="ltr-nums">{formatMoney(s.details.eligible_revenue)}</span>
              </DetailRow>
              <DetailRow label="المستحقات">
                <span className="ltr-nums text-base font-bold">
                  {formatMoney(s.earnings_amount)}
                </span>
              </DetailRow>
              {s.opening_balance !== null ? (
                <DetailRow label="الرصيد قبل الفترة">
                  <span className="ltr-nums">{formatMoney(s.opening_balance)}</span>
                </DetailRow>
              ) : null}
              {s.closing_balance !== null ? (
                <DetailRow label="الرصيد بنهاية الفترة">
                  <span className="ltr-nums">{formatMoney(s.closing_balance)}</span>
                </DetailRow>
              ) : null}
              {s.finalized_at ? (
                <DetailRow label="اعتُمدت">
                  {formatDateTime(s.finalized_at)} · {s.finalized_by?.full_name}
                </DetailRow>
              ) : null}
              {s.void_reason ? <DetailRow label="سبب الإلغاء">{s.void_reason}</DetailRow> : null}
            </dl>
            <Link
              href={`/drivers/${s.driver.id}/account`}
              className="mt-3 inline-block text-sm text-forest-700 hover:underline"
            >
              كشف حساب السائق
            </Link>
          </CardBody>
        </Card>
      </div>
      {s.status !== "VOIDED" && (canWrite || canFinalize) ? (
        <Card className="mt-6">
          <CardHeader title="الإجراءات" />
          <CardBody className="grid gap-6 md:grid-cols-3">
            {draft && canWrite ? (
              <ActionForm
                action={settlementAction.bind(null, s.id, "recalculate")}
                submitLabel="إعادة الحساب"
                variant="secondary"
              />
            ) : null}
            {draft && canFinalize ? (
              <ActionForm
                action={settlementAction.bind(null, s.id, "finalize")}
                submitLabel="اعتماد نهائي وترحيل المستحقات"
                variant="accent"
                confirm="بعد الاعتماد لا تتغير التسوية إلا بإلغائها. متابعة؟"
              />
            ) : null}
            {canFinalize ? (
              <ActionForm
                action={settlementAction.bind(null, s.id, "void")}
                submitLabel="إلغاء التسوية"
                variant="danger"
                confirm="تُلغى التسوية ويُعكس قيد المستحقات. متابعة؟"
              >
                <TextareaField name="reason" label="سبب الإلغاء" rows={2} required />
              </ActionForm>
            ) : null}
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
