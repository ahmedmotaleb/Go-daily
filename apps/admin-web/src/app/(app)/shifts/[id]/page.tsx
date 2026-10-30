import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditTrail } from "@/components/audit-trail";
import { OperationSelect } from "@/components/domain/operation-select";
import { RouteEventsPanel } from "@/components/domain/route-events-panel";
import { ShiftTrackView } from "@/components/map/shift-track-view";
import {
  formatDuration,
  SessionStatusBadge,
  ShiftStatusBadge,
} from "@/components/domain/shift-badges";
import { ActionForm } from "@/components/forms/action-form";
import { TextareaField, TextField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Alert } from "@/components/ui/alert";
import { ShiftExceptions } from "@/components/exceptions/panels";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime, formatNumber } from "@/lib/format";
import { tileConfig } from "@/lib/map-config";
import type { OperationType, Page, Route, RouteEvent, Shift, ShiftTrack } from "@/lib/types";
import {
  cancelShiftAction,
  correctOdometerAction,
  endSessionAction,
  endShiftAction,
  startSessionAction,
  startShiftAction,
} from "../actions";

export const metadata: Metadata = { title: "الوردية" };

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 font-semibold">{value}</p>
    </div>
  );
}

export default async function ShiftDetailPage({ params, searchParams }: PageProps<"/shifts/[id]">) {
  const me = await requirePermission("shifts:read");
  const { id } = await params;
  const sp = await searchParams;
  const shift = await api.get<Shift | null>(`/shifts/${id}`, undefined, { allow404: true });
  if (!shift) notFound();
  const canWrite = can(me, "shifts:write");
  const needsOps = canWrite && (shift.status === "PLANNED" || shift.status === "ACTIVE");
  const [types, routes] = needsOps
    ? await Promise.all([
        api.get<OperationType[]>("/operation-types"),
        api.get<Page<Route>>("/routes", { is_active: true, page_size: 100 }),
      ])
    : [[] as OperationType[], { items: [] as Route[] } as Page<Route>];
  const canTrack = can(me, "tracking:read") && shift.started_at !== null;
  const routedSessions = shift.sessions.filter((s) => s.route && s.status !== "CANCELLED");
  const [track, routeEvents] = canTrack
    ? await Promise.all([
        api.get<ShiftTrack>(`/shifts/${shift.id}/track`),
        Promise.all(
          routedSessions.map((s) =>
            api.get<RouteEvent[]>(`/operation-sessions/${s.id}/route-events`),
          ),
        ),
      ])
    : [null, [] as RouteEvent[][]];

  return (
    <>
      <PageHeader
        title={`وردية ${shift.driver.full_name}`}
        breadcrumb={<Link href="/shifts">الورديات</Link>}
        description={`${shift.vehicle.internal_code} · ${shift.vehicle.plate_number}${shift.source === "DRIVER_APP" ? " · من تطبيق السائق" : ""}`}
        actions={<ShiftStatusBadge status={shift.status} />}
      />
      <Notice code={sp.notice} />
      {shift.assignment_override_reason ? (
        <Alert tone="warning" className="mb-4" title="تشغيل باستثناء">
          السائق لم يكن مكلفًا بهذه المركبة. السبب المسجل: {shift.assignment_override_reason}
        </Alert>
      ) : null}
      {shift.cancel_reason ? (
        <Alert tone="info" className="mb-4" title="وردية ملغاة">
          السبب: {shift.cancel_reason}
        </Alert>
      ) : null}

      <Card className="mb-6">
        <CardBody className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Stat
            label="البداية"
            value={formatDateTime(shift.started_at ?? shift.planned_start_at)}
          />
          <Stat label="النهاية" value={formatDateTime(shift.ended_at ?? shift.planned_end_at)} />
          <Stat
            label="عداد البداية"
            value={<span className="ltr-nums">{formatNumber(shift.start_odometer_km)}</span>}
          />
          <Stat
            label="عداد النهاية"
            value={<span className="ltr-nums">{formatNumber(shift.end_odometer_km)}</span>}
          />
          <Stat
            label="المسافة حسب العداد"
            value={
              shift.odometer_distance_km === null
                ? "—"
                : `${formatNumber(shift.odometer_distance_km)} كم`
            }
          />
          <Stat label="المدة" value={formatDuration(shift.duration_minutes)} />
        </CardBody>
        <p className="border-t border-line px-5 py-2 text-xs text-ink-muted">
          المسافة هنا من قراءات العداد فقط. مسافة GPS معروضة منفصلة في قسم المسار الفعلي ولا يُستبدل
          أي منهما بالآخر.
        </p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="عمليات التشغيل خلال الوردية"
              description="يمكن تنفيذ أكثر من نوع تشغيل في نفس الوردية"
            />
            {shift.sessions.length === 0 ? (
              <EmptyState title="لم يبدأ أي تشغيل بعد" />
            ) : (
              <Table>
                <THead>
                  <tr>
                    <TH>التشغيل</TH>
                    <TH>المسار</TH>
                    <TH>من</TH>
                    <TH>إلى</TH>
                    <TH>الحالة</TH>
                    <TH>
                      <span className="sr-only">إجراءات</span>
                    </TH>
                  </tr>
                </THead>
                <tbody>
                  {shift.sessions.map((s) => (
                    <TR key={s.id}>
                      <TD className="font-medium">{s.operation_type.name_ar}</TD>
                      <TD>{s.route?.name ?? "—"}</TD>
                      <TD className="text-ink-muted">{formatDateTime(s.started_at)}</TD>
                      <TD className="text-ink-muted">{formatDateTime(s.ended_at)}</TD>
                      <TD>
                        <SessionStatusBadge status={s.status} />
                      </TD>
                      <TD>
                        {canWrite && s.status === "ACTIVE" ? (
                          <ActionForm
                            action={endSessionAction.bind(null, s.id, shift.id)}
                            submitLabel="إنهاء التشغيل"
                            variant="secondary"
                          />
                        ) : null}
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            )}
            {canWrite && shift.status === "ACTIVE" ? (
              <CardBody className="border-t border-line">
                <h3 className="mb-3 text-sm font-semibold">
                  {shift.active_session ? "التحويل إلى تشغيل آخر" : "بدء تشغيل"}
                </h3>
                <ActionForm
                  action={startSessionAction.bind(null, shift.id)}
                  submitLabel="بدء التشغيل"
                  variant="accent"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <OperationSelect
                      name="operation"
                      label="نوع التشغيل والمسار"
                      types={types}
                      routes={routes.items}
                      placeholder="اختر"
                      required
                    />
                    <TextField
                      name="start_odometer_km"
                      label="قراءة العداد (اختياري)"
                      inputMode="numeric"
                    />
                  </div>
                  <TextField name="notes" label="ملاحظات" />
                  {shift.active_session ? (
                    <p className="text-xs text-ink-muted">
                      سينتهي التشغيل الحالي تلقائيًا عند بدء التشغيل الجديد.
                    </p>
                  ) : null}
                </ActionForm>
              </CardBody>
            ) : null}
          </Card>
          {track ? (
            <Card>
              <CardHeader
                title="المسار الفعلي حسب GPS"
                description="إعادة المسار، التوقفات، الانقطاعات والخط الزمني"
              />
              <CardBody>
                <ShiftTrackView tiles={tileConfig()} track={track} />
              </CardBody>
            </Card>
          ) : null}
          {canTrack && routedSessions.length > 0 ? (
            <Card>
              <CardHeader
                title="الدورات والمحطات"
                description="محسوبة تلقائيًا من نقاط GPS مع إمكانية التصحيح الموثق"
              />
              <CardBody className="space-y-6">
                {routedSessions.map((s, i) => (
                  <RouteEventsPanel
                    key={s.id}
                    session={s}
                    shiftId={shift.id}
                    events={routeEvents[i] ?? []}
                    canWrite={canWrite}
                  />
                ))}
              </CardBody>
            </Card>
          ) : null}
          {can(me, "exceptions:read") ? <ShiftExceptions shiftId={shift.id} /> : null}
          {shift.notes ? (
            <Card>
              <CardHeader title="ملاحظات" />
              <CardBody>
                <p className="text-sm whitespace-pre-line">{shift.notes}</p>
              </CardBody>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          {canWrite && shift.status === "PLANNED" ? (
            <Card>
              <CardHeader title="بدء الوردية" />
              <CardBody>
                <ActionForm
                  action={startShiftAction.bind(null, shift.id)}
                  submitLabel="بدء الوردية"
                  variant="accent"
                >
                  <TextField
                    name="start_odometer_km"
                    label="قراءة العداد (كم)"
                    inputMode="numeric"
                    required
                  />
                  <TextField
                    name="started_at"
                    label="وقت البدء"
                    type="datetime-local"
                    hint="اتركه فارغًا للآن"
                  />
                  <OperationSelect
                    name="operation"
                    label="التشغيل الأول"
                    types={types}
                    routes={routes.items}
                    placeholder={
                      shift.planned_operation_type
                        ? `حسب الخطة: ${shift.planned_operation_type.name_ar}`
                        : "بدون"
                    }
                  />
                  <TextField
                    name="assignment_override_reason"
                    label="سبب الاستثناء (اختياري)"
                    hint="إن لم يكن السائق مكلفًا بالمركبة"
                  />
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
          {canWrite && shift.status === "ACTIVE" ? (
            <Card>
              <CardHeader title="إنهاء الوردية" />
              <CardBody>
                <ActionForm
                  action={endShiftAction.bind(null, shift.id)}
                  submitLabel="إنهاء الوردية"
                  confirm="إنهاء الوردية وإغلاق التشغيل الحالي؟"
                >
                  <TextField
                    name="end_odometer_km"
                    label="قراءة العداد عند الانتهاء (كم)"
                    inputMode="numeric"
                    required
                    hint={`قراءة البداية: ${formatNumber(shift.start_odometer_km)}`}
                  />
                  <TextField
                    name="ended_at"
                    label="وقت الانتهاء"
                    type="datetime-local"
                    hint="اتركه فارغًا للآن"
                  />
                  <TextareaField name="notes" label="ملاحظات" rows={2} />
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
          {canWrite && shift.status === "COMPLETED" ? (
            <Card>
              <CardHeader
                title="تصحيح قراءات العداد"
                description="يتم تسجيل القيم القديمة والجديدة والسبب"
              />
              <CardBody>
                <ActionForm
                  action={correctOdometerAction.bind(null, shift.id)}
                  submitLabel="حفظ التصحيح"
                  variant="secondary"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <TextField
                      name="start_odometer_km"
                      label="عداد البداية"
                      inputMode="numeric"
                      defaultValue={shift.start_odometer_km}
                    />
                    <TextField
                      name="end_odometer_km"
                      label="عداد النهاية"
                      inputMode="numeric"
                      defaultValue={shift.end_odometer_km}
                    />
                  </div>
                  <TextField name="reason" label="سبب التصحيح" required />
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
          {canWrite && (shift.status === "PLANNED" || shift.status === "ACTIVE") ? (
            <Card>
              <CardHeader title="إلغاء الوردية" />
              <CardBody>
                <ActionForm
                  action={cancelShiftAction.bind(null, shift.id)}
                  submitLabel="إلغاء الوردية"
                  variant="danger"
                  confirm="إلغاء هذه الوردية؟"
                >
                  <TextField name="reason" label="السبب" required />
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
          {can(me, "audit:read") ? (
            <AuditTrail entityType="shift" entityId={shift.id} title="سجل الوردية" />
          ) : null}
        </div>
      </div>
    </>
  );
}
