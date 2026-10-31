import Link from "next/link";
import type { ReactNode } from "react";
import { reviewAction } from "@/app/(app)/finance/actions";
import { ActionForm } from "@/components/forms/action-form";
import { TextareaField, TextField } from "@/components/forms/fields";
import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { FINANCE_PAGE, type FinanceResource } from "@/lib/finance-paths";
import {
  RECORD_SOURCE_LABELS,
  RECORD_STATUS_LABELS,
  SETTLEMENT_STATUS_LABELS,
} from "@/lib/finance-labels";
import type { RecordStatus, Reviewable, SettlementStatus } from "@/lib/finance-types";
import { formatDateTime } from "@/lib/format";

const TONES: Record<RecordStatus, Tone> = {
  SUBMITTED: "warning",
  APPROVED: "success",
  REJECTED: "danger",
  VOIDED: "neutral",
};

export function RecordStatusBadge({ status }: { status: RecordStatus }) {
  return <Badge tone={TONES[status]}>{RECORD_STATUS_LABELS[status]}</Badge>;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-2 py-1.5 text-sm">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="font-medium text-ink">{children}</dd>
    </div>
  );
}

/** Lifecycle facts and review actions shared by every financial record. */
export function ReviewPanel({
  resource,
  record,
  canReview,
  managedBy,
}: {
  resource: FinanceResource;
  record: Reviewable;
  canReview: boolean;
  /** Set when the record is generated from another one and reviewed there. */
  managedBy?: ReactNode;
}) {
  const page = FINANCE_PAGE[resource];
  const id = record.id;
  return (
    <Card>
      <CardHeader title="الحالة والمراجعة" actions={<RecordStatusBadge status={record.status} />} />
      <CardBody className="space-y-4">
        <dl className="divide-y divide-line">
          <Row label="المصدر">{RECORD_SOURCE_LABELS[record.source]}</Row>
          <Row label="أُدخل بواسطة">
            {record.created_by?.full_name ?? "—"} · {formatDateTime(record.created_at)}
          </Row>
          {record.reviewed_at ? (
            <Row label={record.status === "REJECTED" ? "رُفض بواسطة" : "رُوجع بواسطة"}>
              {record.reviewed_by?.full_name ?? "—"} · {formatDateTime(record.reviewed_at)}
            </Row>
          ) : null}
          {record.review_note ? <Row label="ملاحظة المراجعة">{record.review_note}</Row> : null}
          {record.voided_at ? (
            <Row label="أُلغي بواسطة">
              {record.voided_by?.full_name ?? "—"} · {formatDateTime(record.voided_at)}
            </Row>
          ) : null}
          {record.void_reason ? <Row label="سبب الإلغاء">{record.void_reason}</Row> : null}
          {record.corrects_id ? (
            <Row label="يصحح السجل">
              <Link
                href={`${page}/${record.corrects_id}`}
                className="text-forest-700 hover:underline"
              >
                عرض السجل الأصلي
              </Link>
            </Row>
          ) : null}
          {record.corrected_by_id ? (
            <Row label="صُحح بالسجل">
              <Link
                href={`${page}/${record.corrected_by_id}`}
                className="text-forest-700 hover:underline"
              >
                عرض السجل المصحح
              </Link>
            </Row>
          ) : null}
        </dl>
        {managedBy ? <p className="text-sm text-ink-muted">{managedBy}</p> : null}
        {canReview && !managedBy && record.status === "SUBMITTED" ? (
          <div className="grid gap-4 border-t border-line pt-4 md:grid-cols-2">
            <ActionForm
              action={reviewAction.bind(null, resource, id, "approve")}
              submitLabel="اعتماد"
              variant="accent"
              confirm="بعد الاعتماد يدخل السجل في الإجماليات (وحساب السائق إن وجد) ولا يُعدّل إلا بتصحيح موثق. متابعة؟"
            >
              <TextField name="note" label="ملاحظة (اختياري)" />
            </ActionForm>
            <ActionForm
              action={reviewAction.bind(null, resource, id, "reject")}
              submitLabel="رفض وإعادة للتعديل"
              variant="secondary"
            >
              <TextField name="reason" label="سبب الرفض" required />
            </ActionForm>
          </div>
        ) : null}
        {canReview && !managedBy && record.status !== "VOIDED" ? (
          <details className="border-t border-line pt-4">
            <summary className="cursor-pointer text-sm font-medium text-danger">
              إلغاء السجل
            </summary>
            <ActionForm
              action={reviewAction.bind(null, resource, id, "void")}
              submitLabel="إلغاء السجل"
              variant="danger"
              confirm="يُلغى السجل ويبقى محفوظًا مع السبب. متابعة؟"
              className="mt-3"
            >
              <TextareaField name="reason" label="سبب الإلغاء" rows={2} required />
            </ActionForm>
          </details>
        ) : null}
      </CardBody>
    </Card>
  );
}

const SETTLEMENT_TONES: Record<SettlementStatus, Tone> = {
  DRAFT: "warning",
  FINALIZED: "success",
  VOIDED: "neutral",
};

export function SettlementStatusBadge({ status }: { status: SettlementStatus }) {
  return <Badge tone={SETTLEMENT_TONES[status]}>{SETTLEMENT_STATUS_LABELS[status]}</Badge>;
}
