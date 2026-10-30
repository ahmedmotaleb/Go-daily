import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Evidence } from "@/components/exceptions/evidence";
import { DetailRow } from "@/components/finance/filters";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextareaField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { AuditTrail } from "@/components/audit-trail";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import {
  LABEL_AR,
  SEVERITY_AR,
  SEVERITY_TONE,
  STATUS_AR,
  STATUS_TONE,
  SUBJECT_AR,
  SUBJECT_PATH,
  TRANSITION_AR,
} from "@/lib/exception-labels";
import type { OperationalException } from "@/lib/exception-types";
import { formatDateTime } from "@/lib/format";
import { reviewExceptionAction } from "../actions";

export const metadata: Metadata = { title: "حالة للمراجعة" };

export default async function ExceptionPage({
  params,
  searchParams,
}: PageProps<"/exceptions/[id]">) {
  const me = await requirePermission("exceptions:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const e = await api.get<OperationalException | null>(`/exceptions/${id}`, undefined, {
    allow404: true,
  });
  if (!e) notFound();
  const subjectBase = e.subject_type ? SUBJECT_PATH[e.subject_type] : undefined;
  const canReview = can(me, "exceptions:review") && e.allowed_transitions.length > 0;

  return (
    <>
      <PageHeader
        title={e.rule_title}
        description={e.summary}
        breadcrumb={<Link href="/exceptions">حالات للمراجعة</Link>}
        actions={
          <div className="flex gap-2">
            <Badge tone={e.label === "REVIEW_REQUIRED" ? "warning" : "info"}>
              {LABEL_AR[e.label]}
            </Badge>
            <Badge tone={STATUS_TONE[e.status]}>{STATUS_AR[e.status]}</Badge>
          </div>
        }
      />
      <Notice code={typeof notice === "string" ? notice : undefined} />
      <Alert tone="info" className="mb-4">
        هذه إشارة آلية من قاعدة واضحة، وليست دليلًا على مخالفة. راجع الأدلة واطلب التوضيح قبل أي
        استنتاج.
      </Alert>
      {e.cleared_at ? (
        <Alert tone="success" className="mb-4">
          آخر فحص ({formatDateTime(e.cleared_at)}) لم يعد يجد هذه الحالة، ربما بعد تصحيح البيانات.
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="الأدلة"
              description="الحقائق والحدود التي استخدمتها القاعدة، كما سُجلت"
            />
            <CardBody>
              <Evidence evidence={e.evidence} />
            </CardBody>
          </Card>
          {canReview ? (
            <Card>
              <CardHeader
                title="تسجيل المراجعة"
                description="الإغلاق يحتاج نتيجة مكتوبة، والتصعيد وإعادة الفتح يحتاجان سببًا"
              />
              <CardBody>
                <ActionForm
                  action={reviewExceptionAction.bind(null, e.id)}
                  submitLabel="حفظ"
                  version={e.updated_at}
                >
                  <SelectField
                    name="status"
                    label="الإجراء"
                    placeholder="اختر الإجراء"
                    options={e.allowed_transitions.map((s) => ({
                      value: s,
                      label: TRANSITION_AR[s],
                    }))}
                    required
                  />
                  <TextareaField name="notes" label="ملاحظات المراجعة" rows={2} />
                  <TextareaField name="resolution" label="النتيجة (عند الإغلاق)" rows={2} />
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="التفاصيل" />
            <CardBody>
              <dl className="divide-y divide-line">
                <DetailRow label="الأهمية">
                  <Badge tone={SEVERITY_TONE[e.severity]}>{SEVERITY_AR[e.severity]}</Badge>
                </DetailRow>
                <DetailRow label="وقت الحدوث">
                  <span className="ltr-nums">
                    {formatDateTime(e.occurred_at)}
                    {e.occurred_until ? ` — ${formatDateTime(e.occurred_until)}` : ""}
                  </span>
                </DetailRow>
                <DetailRow label="اكتُشفت">
                  <span className="ltr-nums">{formatDateTime(e.detected_at)}</span>
                </DetailRow>
                {e.vehicle ? (
                  <DetailRow label="المركبة">
                    <Link href={`/vehicles/${e.vehicle.id}`} className="ltr-nums hover:underline">
                      {e.vehicle.name}
                    </Link>
                  </DetailRow>
                ) : null}
                {e.driver ? (
                  <DetailRow label="السائق">
                    <Link href={`/drivers/${e.driver.id}`} className="hover:underline">
                      {e.driver.name}
                    </Link>
                  </DetailRow>
                ) : null}
                {e.shift_id ? (
                  <DetailRow label="الوردية">
                    <Link
                      href={`/shifts/${e.shift_id}`}
                      className="text-forest-700 hover:underline"
                    >
                      عرض الوردية والمسار
                    </Link>
                  </DetailRow>
                ) : null}
                {subjectBase && e.subject_id && e.subject_type ? (
                  <DetailRow label="السجل">
                    <Link
                      href={`${subjectBase}/${e.subject_id}`}
                      className="text-forest-700 hover:underline"
                    >
                      عرض {SUBJECT_AR[e.subject_type]}
                    </Link>
                  </DetailRow>
                ) : null}
                {e.reviewer ? (
                  <DetailRow label="آخر مراجعة">
                    {e.reviewer.full_name} ·{" "}
                    <span className="ltr-nums">{formatDateTime(e.reviewed_at)}</span>
                  </DetailRow>
                ) : null}
                {e.review_notes ? <DetailRow label="ملاحظات">{e.review_notes}</DetailRow> : null}
                {e.resolution ? <DetailRow label="النتيجة">{e.resolution}</DetailRow> : null}
              </dl>
            </CardBody>
          </Card>
          {can(me, "audit:read") ? (
            <AuditTrail entityType="operational_exception" entityId={e.id} />
          ) : null}
        </div>
      </div>
    </>
  );
}
