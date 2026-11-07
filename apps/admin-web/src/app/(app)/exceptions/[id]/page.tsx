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
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { ShiftTrackView } from "@/components/map/shift-track-view";
import { DayTimeline } from "@/components/vehicles/day-timeline";
import type { AttachmentOwner } from "@/lib/attachment-types";
import { tileConfig } from "@/lib/map-config";
import { cairoDate } from "@/lib/search";
import type { ShiftTrack, TimelineItem } from "@/lib/types";
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

/** Who may see each record's files (mirrors the API's attachment rules). */
const ATTACHMENT_READ: Partial<Record<AttachmentOwner, string>> = {
  fuel_transaction: "fuel:read",
  expense: "expenses:read",
  revenue_entry: "revenue:read",
  ride_hailing_statement: "revenue:read",
  maintenance_record: "maintenance:read",
  vehicle: "vehicles:read",
};

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
  // Investigation workspace (U28): everything recorded around the case, each
  // part only for users allowed to read it (the API checks again).
  const day = cairoDate(e.occurred_at);
  const subjectOwner = e.subject_type as AttachmentOwner | null;
  const subjectRead = subjectOwner ? ATTACHMENT_READ[subjectOwner] : undefined;
  const [related, track, timeline] = await Promise.all([
    api.get<OperationalException[]>(`/exceptions/${e.id}/related`),
    e.shift_id && can(me, "tracking:read")
      ? api.get<ShiftTrack>(`/shifts/${e.shift_id}/track`)
      : null,
    e.vehicle && can(me, "vehicles:read")
      ? api.get<TimelineItem[]>(`/vehicles/${e.vehicle.id}/timeline`, { day })
      : null,
  ]);

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
            <CardHeader title="لماذا ظهرت هذه الحالة" />
            <CardBody className="space-y-4">
              <div>
                <h3 className="mb-1 text-xs font-semibold text-ink-muted">سبب القاعدة</h3>
                <p className="text-sm">{e.reason}</p>
              </div>
              <div className="rounded-[var(--radius-control)] bg-[#eef4f0] px-3.5 py-3">
                <h3 className="mb-1 text-xs font-semibold text-primary">ما المطلوب مراجعته</h3>
                <p className="text-sm text-ink">{e.review_action}</p>
              </div>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="القيم المرصودة" description="الحقائق كما سُجلت وقت الفحص" />
            <CardBody>
              <Evidence evidence={e.observed} />
            </CardBody>
          </Card>
          {Object.keys(e.thresholds).length ? (
            <Card>
              <CardHeader title="الحدود المستخدمة" description="الإعدادات التي قورنت بها القيم" />
              <CardBody>
                <Evidence evidence={e.thresholds} />
              </CardBody>
            </Card>
          ) : null}
          {track ? (
            <Card>
              <CardHeader
                title="المسار والتتبع"
                description="مسار الوردية ونقاط التتبع والانقطاعات ومقارنة العداد كما سُجلت"
              />
              <CardBody>
                <ShiftTrackView tiles={tileConfig()} track={track} />
              </CardBody>
            </Card>
          ) : null}
          {timeline && e.vehicle ? (
            <DayTimeline
              vehicleId={e.vehicle.id}
              day={day}
              items={timeline}
              picker={false}
              title={`يوم السيارة ${day}`}
            />
          ) : null}
          {subjectOwner && subjectRead && e.subject_id && can(me, subjectRead) ? (
            <AttachmentsPanel
              ownerType={subjectOwner}
              ownerId={e.subject_id}
              returnPath={`/exceptions/${e.id}`}
              canWrite={false}
              locked
              title={`مرفقات ${SUBJECT_AR[subjectOwner] ?? "السجل"}`}
            />
          ) : null}
          {e.shift_id && can(me, "shifts:read") ? (
            <AttachmentsPanel
              ownerType="shift"
              ownerId={e.shift_id}
              returnPath={`/exceptions/${e.id}`}
              canWrite={false}
              locked
              title="صور الوردية (العداد)"
            />
          ) : null}
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
                    <Link href={`/shifts/${e.shift_id}`} className="text-primary hover:underline">
                      عرض الوردية والمسار
                    </Link>
                  </DetailRow>
                ) : null}
                {subjectBase && e.subject_id && e.subject_type ? (
                  <DetailRow label="السجل">
                    <Link
                      href={`${subjectBase}/${e.subject_id}`}
                      className="text-primary hover:underline"
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
          <Card>
            <CardHeader
              title="حالات قريبة"
              description="حالات على نفس السيارة أو السائق خلال يوم؛ القرب وحده ليس دليلًا"
            />
            {related.length === 0 ? (
              <p className="px-5 py-4 text-sm text-ink-muted">لا توجد حالات أخرى قريبة.</p>
            ) : (
              <ul className="divide-y divide-line">
                {related.map((r) => (
                  <li key={r.id} className="px-5 py-3">
                    <Link
                      href={`/exceptions/${r.id}`}
                      className="text-sm font-medium hover:underline"
                    >
                      {r.rule_title}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                      <span className="ltr-nums">{formatDateTime(r.occurred_at)}</span>
                      <Badge tone={SEVERITY_TONE[r.severity]}>{SEVERITY_AR[r.severity]}</Badge>
                      <Badge tone={STATUS_TONE[r.status]}>{STATUS_AR[r.status]}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {can(me, "audit:read") ? (
            <AuditTrail entityType="operational_exception" entityId={e.id} />
          ) : null}
        </div>
      </div>
    </>
  );
}
