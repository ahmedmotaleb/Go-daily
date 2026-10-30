import type { Metadata } from "next";
import Link from "next/link";
import {
  addReceiptAction,
  saveRevenueAction,
  voidReceiptAction,
} from "@/app/(app)/finance/actions";
import { DetailRow } from "@/components/finance/filters";
import { ReceiptForm, RevenueForm } from "@/components/finance/revenue-form";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { ReviewPanel } from "@/components/finance/review";
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
import {
  PAYMENT_METHOD_LABELS,
  RECEIVED_BY_LABELS,
  REVENUE_KIND_LABELS,
} from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { RevenueEntry } from "@/lib/finance-types";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import type { OperationType } from "@/lib/types";

export const metadata: Metadata = { title: "إيراد" };

export default async function RevenueDetailPage({
  params,
  searchParams,
}: PageProps<"/finance/revenue/[id]">) {
  const me = await requirePermission("revenue:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const r = await api.get<RevenueEntry>(`/revenue/${id}`);
  const fromStatement = r.statement_id !== null;
  const canWrite = can(me, "revenue:write") && !fromStatement;
  const canReview = can(me, "revenue:approve");
  const canEdit = canWrite && (r.status === "SUBMITTED" || r.status === "REJECTED");
  const canCorrect = canReview && !fromStatement && r.status === "APPROVED";
  const canReceive =
    canWrite &&
    (r.status === "SUBMITTED" || r.status === "APPROVED") &&
    Number(r.outstanding_amount) > 0;
  const [types, fleet] =
    canEdit || canCorrect
      ? await Promise.all([api.get<OperationType[]>("/operation-types"), fleetOptions()])
      : [[], { vehicles: [], drivers: [] }];
  const typeOptions = types.map((t) => ({ value: t.id, label: t.name_ar }));

  return (
    <>
      <PageHeader
        title={`${REVENUE_KIND_LABELS[r.kind]} — ${r.vehicle.name}`}
        description={formatDate(r.occurred_on)}
        breadcrumb={<Link href="/finance/revenue">الإيرادات</Link>}
      />
      <Notice code={notice} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="التفاصيل" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="المركبة">
                <Link href={`/vehicles/${r.vehicle.id}`} className="ltr-nums hover:underline">
                  {r.vehicle.name}
                </Link>
              </DetailRow>
              <DetailRow label="السائق">{r.driver?.name ?? "—"}</DetailRow>
              <DetailRow label="نوع التشغيل">{r.operation_type?.name ?? "غير محدد"}</DetailRow>
              {r.period_start ? (
                <DetailRow label="فترة الخدمة">
                  {formatDate(r.period_start)} — {formatDate(r.period_end)}
                </DetailRow>
              ) : null}
              <DetailRow label="المستحق">
                <span className="ltr-nums text-base font-bold">{formatMoney(r.amount)}</span>
              </DetailRow>
              {Number(r.fees_withheld) > 0 ? (
                <DetailRow label="عمولة مخصومة من المصدر">
                  <span className="ltr-nums">{formatMoney(r.fees_withheld)}</span>
                </DetailRow>
              ) : null}
              <DetailRow label="المستلم">
                <span className="ltr-nums">
                  {formatMoney(r.received_amount)} (نقدي {formatMoney(r.received_cash)} · إلكتروني{" "}
                  {formatMoney(r.received_electronic)})
                </span>
              </DetailRow>
              <DetailRow label="المتبقي">
                <span className="ltr-nums">{formatMoney(r.outstanding_amount)}</span>
              </DetailRow>
              {r.loops_count !== null ? (
                <DetailRow label="عدد الدورات">{formatNumber(r.loops_count)}</DetailRow>
              ) : null}
              {r.customer_name ? <DetailRow label="العميل">{r.customer_name}</DetailRow> : null}
              {r.reference ? <DetailRow label="مرجع">{r.reference}</DetailRow> : null}
              {r.notes ? <DetailRow label="ملاحظات">{r.notes}</DetailRow> : null}
            </dl>
          </CardBody>
        </Card>
        <ReviewPanel
          resource="revenue"
          record={r}
          canReview={canReview}
          managedBy={
            fromStatement ? (
              <>
                هذا الإيراد ناتج عن{" "}
                <Link
                  href={`/finance/ride-hailing/${r.statement_id}`}
                  className="text-forest-700 hover:underline"
                >
                  كشف منصة
                </Link>{" "}
                ويُراجع أو يُلغى من خلاله.
              </>
            ) : undefined
          }
        />
      </div>

      <div className="mt-6">
        <AttachmentsPanel
          ownerType="revenue_entry"
          ownerId={r.id}
          returnPath={`/finance/revenue/${r.id}`}
          canWrite={canWrite}
          locked={r.status === "APPROVED" || r.status === "VOIDED"}
          title="مستندات الإيراد"
        />
      </div>

      <Card className="mt-6">
        <CardHeader
          title="المبالغ المستلمة"
          description="ما يستلمه السائق يُسجل عهدة على حسابه حتى التسليم"
        />
        {r.receipts.length === 0 ? (
          <EmptyState title="لم يُستلم أي مبلغ بعد" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>الوقت</TH>
                <TH>المبلغ</TH>
                <TH>الطريقة</TH>
                <TH>المستلم</TH>
                <TH>مرجع</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {r.receipts.map((rc) => (
                <TR key={rc.id}>
                  <TD>{formatDateTime(rc.received_at)}</TD>
                  <TD className="ltr-nums font-medium">{formatMoney(rc.amount)}</TD>
                  <TD>{PAYMENT_METHOD_LABELS[rc.method]}</TD>
                  <TD>{RECEIVED_BY_LABELS[rc.received_by]}</TD>
                  <TD>{rc.reference ?? "—"}</TD>
                  <TD>
                    {rc.voided_at ? (
                      <Badge>ملغي: {rc.void_reason}</Badge>
                    ) : canReview && !fromStatement ? (
                      <details>
                        <summary className="cursor-pointer text-xs text-danger">إلغاء</summary>
                        <ActionForm
                          action={voidReceiptAction.bind(null, rc.id, r.id)}
                          submitLabel="إلغاء المقبوض"
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
              ))}
            </tbody>
          </Table>
        )}
        {canReceive ? (
          <CardBody className="border-t border-line">
            <ReceiptForm action={addReceiptAction.bind(null, r.id)} hasDriver={r.driver !== null} />
          </CardBody>
        ) : null}
      </Card>

      {canEdit ? (
        <Card className="mt-6">
          <CardHeader title="تعديل الإيراد" description="التعديل متاح قبل الاعتماد فقط" />
          <CardBody>
            <RevenueForm
              action={saveRevenueAction.bind(null, "edit", r.id)}
              mode="edit"
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              operationTypes={typeOptions}
              record={r}
              canApprove={false}
            />
          </CardBody>
        </Card>
      ) : null}
      {canCorrect ? (
        <Card className="mt-6">
          <CardHeader
            title="تصحيح إيراد معتمد"
            description="يُلغى هذا السجل وينشأ سجل جديد مرتبط به، وتنتقل إليه المبالغ المستلمة"
          />
          <CardBody>
            <RevenueForm
              action={saveRevenueAction.bind(null, "correct", r.id)}
              mode="correct"
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              operationTypes={typeOptions}
              record={r}
              canApprove
            />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
