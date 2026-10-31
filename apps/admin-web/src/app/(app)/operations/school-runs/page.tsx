import { WEEKDAY_LABELS_AR, WEEKDAY_ORDER } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import type { Driver, Page, Route, SchoolRun, SchoolRunStatus, Vehicle } from "@/lib/types";
import { correctRunStatusAction, generateRunsAction } from "./actions";

export const metadata: Metadata = { title: "دورات المدارس" };

const STATUS: Record<SchoolRunStatus, { label: string; tone: Tone }> = {
  SCHEDULED: { label: "مجدولة", tone: "info" },
  IN_PROGRESS: { label: "جارية", tone: "active" },
  COMPLETED: { label: "مكتملة (موثقة بـ GPS)", tone: "success" },
  COMPLETED_UNVERIFIED: { label: "مراجعة مطلوبة — بدون دليل GPS", tone: "warning" },
  MISSED: { label: "حالة غير معتادة — لم يتم تسجيل تشغيل", tone: "danger" },
  CANCELLED: { label: "ملغاة", tone: "neutral" },
};

function todayCairo(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo" }).format(new Date());
}

export default async function SchoolRunsPage({
  searchParams,
}: PageProps<"/operations/school-runs">) {
  const me = await requirePermission("operations:read");
  const sp = await searchParams;
  const day =
    typeof sp.day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(sp.day) ? sp.day : todayCairo();
  const canWrite = can(me, "operations:write");
  const [runs, routes, vehicles, drivers] = await Promise.all([
    api.get<Page<SchoolRun>>("/school-runs", { date_from: day, date_to: day, page_size: 100 }),
    canWrite
      ? api.get<Page<Route>>("/routes", { is_active: true, page_size: 100 })
      : Promise.resolve(null),
    canWrite
      ? api.get<Page<Vehicle>>("/vehicles", { is_active: true, page_size: 100 })
      : Promise.resolve(null),
    canWrite
      ? api.get<Page<Driver>>("/drivers", { employment_status: "ACTIVE", page_size: 100 })
      : Promise.resolve(null),
  ]);
  const schoolRoutes = (routes?.items ?? []).filter(
    (r) => r.operation_type.kind === "SCHOOL_ROUTE",
  );

  return (
    <>
      <PageHeader
        title="دورات المدارس"
        breadcrumb={<Link href="/operations">التشغيل</Link>}
        description="الدورات المجدولة وحالة تنفيذها حسب أدلة GPS"
      />
      <Notice code={sp.notice} />
      <Card className="mb-6">
        <form className="flex flex-wrap items-end gap-2 border-b border-line px-4 py-3">
          <label htmlFor="day" className="text-sm text-ink-muted">
            اليوم
          </label>
          <Input id="day" name="day" type="date" defaultValue={day} className="w-44" />
          <Button type="submit" variant="secondary">
            عرض
          </Button>
          <span className="text-sm text-ink-muted">{formatDate(day)}</span>
        </form>
        {runs.items.length === 0 ? (
          <EmptyState title="لا توجد دورات مجدولة لهذا اليوم" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>المسار</TH>
                <TH>الموعد</TH>
                <TH>المركبة / السائق</TH>
                <TH>التنفيذ الفعلي</TH>
                <TH>الحالة</TH>
                <TH>
                  <span className="sr-only">تصحيح</span>
                </TH>
              </tr>
            </THead>
            <tbody>
              {runs.items.map((r) => (
                <TR key={r.id}>
                  <TD>
                    <div className="font-medium">{r.route.name}</div>
                    {r.label ? <div className="text-xs text-ink-muted">{r.label}</div> : null}
                  </TD>
                  <TD className="text-ink-muted">
                    {formatDateTime(r.scheduled_start_at)} –{" "}
                    {formatDateTime(r.scheduled_end_at).split("، ")[1] ?? ""}
                  </TD>
                  <TD>
                    <span className="ltr-nums">{r.vehicle.internal_code}</span>
                    <div className="text-xs text-ink-muted">{r.driver?.full_name ?? "—"}</div>
                  </TD>
                  <TD className="text-sm">
                    {r.actual_start_at ? (
                      <>
                        {formatDateTime(r.actual_start_at)}
                        {r.shift_id ? (
                          <Link
                            href={`/shifts/${r.shift_id}`}
                            className="ms-2 text-xs text-forest-700 hover:underline"
                          >
                            الوردية
                          </Link>
                        ) : null}
                        <div className="text-xs text-ink-muted">
                          {r.evidence.reached_destination
                            ? "✔ وصل لنقطة النهاية (GPS)"
                            : "لا يوجد وصول مسجل لنقطة النهاية"}
                        </div>
                      </>
                    ) : (
                      "—"
                    )}
                  </TD>
                  <TD>
                    <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
                    {r.status_reason?.startsWith("manual:") ? (
                      <div className="mt-1 text-xs text-ink-muted">
                        {r.status_reason.replace("manual: ", "تصحيح: ")}
                      </div>
                    ) : null}
                  </TD>
                  <TD>
                    {canWrite && r.status !== "IN_PROGRESS" ? (
                      <details>
                        <summary className="cursor-pointer text-xs text-ink-muted">تصحيح</summary>
                        <ActionForm
                          action={correctRunStatusAction.bind(null, r.id)}
                          submitLabel="حفظ"
                          variant="secondary"
                          className="mt-2 w-64"
                        >
                          <input type="hidden" name="day" value={day} />
                          <SelectField
                            name="status"
                            label="الحالة"
                            defaultValue={r.status}
                            options={(
                              [
                                "SCHEDULED",
                                "COMPLETED",
                                "COMPLETED_UNVERIFIED",
                                "MISSED",
                                "CANCELLED",
                              ] as const
                            ).map((s) => ({ value: s, label: STATUS[s].label }))}
                          />
                          <TextField name="reason" label="السبب" required />
                        </ActionForm>
                      </details>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {canWrite ? (
        <Card>
          <CardHeader
            title="جدولة دورات"
            description="إنشاء دورات لمسار مدرسة على فترة زمنية (يتم تخطي المكرر)"
          />
          <CardBody>
            {schoolRoutes.length === 0 ? (
              <p className="text-sm text-ink-muted">
                لا توجد مسارات مدارس. أضف مسارًا بنوع &quot;دورة مدرسة&quot; من صفحة{" "}
                <Link href="/operations/routes/new" className="text-forest-700 underline">
                  التشغيل
                </Link>
                .
              </p>
            ) : (
              <ActionForm action={generateRunsAction} submitLabel="إنشاء الدورات" variant="accent">
                <div className="grid gap-3 sm:grid-cols-3">
                  <SelectField
                    name="route_id"
                    label="مسار المدرسة"
                    options={schoolRoutes.map((r) => ({ value: r.id, label: r.name }))}
                    placeholder="اختر"
                    required
                  />
                  <SelectField
                    name="vehicle_id"
                    label="المركبة"
                    options={(vehicles?.items ?? []).map((v) => ({
                      value: v.id,
                      label: `${v.internal_code} · ${v.plate_number}`,
                    }))}
                    placeholder="اختر"
                    required
                  />
                  <SelectField
                    name="driver_id"
                    label="السائق (اختياري)"
                    options={(drivers?.items ?? []).map((d) => ({
                      value: d.id,
                      label: d.full_name,
                    }))}
                    placeholder="يحدد عند التشغيل"
                  />
                  <TextField
                    name="date_from"
                    label="من تاريخ"
                    type="date"
                    defaultValue={day}
                    required
                  />
                  <TextField
                    name="date_to"
                    label="إلى تاريخ"
                    type="date"
                    defaultValue={day}
                    required
                  />
                  <TextField name="label" label="الوصف" placeholder="صباحي / بعد الظهر" />
                  <TextField name="start_time" label="بداية الدورة" type="time" required />
                  <TextField name="end_time" label="نهاية الدورة" type="time" required />
                </div>
                <fieldset>
                  <legend className="mb-2 text-sm font-medium">
                    الأيام (افتراضيًا: أيام تشغيل المسار)
                  </legend>
                  <div className="flex flex-wrap gap-3">
                    {WEEKDAY_ORDER.map((d) => (
                      <label key={d} className="inline-flex items-center gap-1.5 text-sm">
                        <input
                          type="checkbox"
                          name="weekdays"
                          value={d}
                          className="size-4 accent-forest-700"
                        />
                        {WEEKDAY_LABELS_AR[d]}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </ActionForm>
            )}
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
