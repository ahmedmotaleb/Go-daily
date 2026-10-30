import { Bell, Bus, Clock, MapPin, UsersRound, CalendarDays, type LucideIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { ExpiryBadge } from "@/components/domain/badges";
import { formatDuration } from "@/components/domain/shift-badges";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { actionLabel } from "@/lib/audit-labels";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { DashboardSummary } from "@/lib/types";

export const metadata: Metadata = { title: "لوحة التحكم" };

const DOC_LABELS: Record<DashboardSummary["expiring_documents"][number]["kind"], string> = {
  VEHICLE_LICENSE: "رخصة مركبة",
  VEHICLE_INSURANCE: "تأمين مركبة",
  DRIVER_LICENSE: "رخصة قيادة",
};

const ENTITY_PATHS: Record<string, string> = {
  vehicle: "/vehicles",
  driver: "/drivers",
  shift: "/shifts",
  route: "/operations/routes",
};

function Kpi({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  accent?: boolean;
}) {
  return (
    <Card>
      <CardBody className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm text-ink-muted">{label}</p>
          <p className="ltr-nums mt-1 text-3xl font-bold text-ink">{formatNumber(value)}</p>
        </div>
        <span
          className={
            accent
              ? "flex size-11 items-center justify-center rounded-full bg-lime-100 text-forest-800"
              : "flex size-11 items-center justify-center rounded-full bg-forest-50 text-forest-700"
          }
        >
          <Icon className="size-5" aria-hidden="true" />
        </span>
      </CardBody>
    </Card>
  );
}

function Placeholder({
  icon: Icon,
  title,
  text,
}: {
  icon: LucideIcon;
  title: string;
  text: string;
}) {
  return (
    <Card className="border-dashed">
      <CardBody className="flex items-start gap-3">
        <Icon className="mt-0.5 size-5 shrink-0 text-ink-muted" aria-hidden="true" />
        <div>
          <p className="font-semibold text-ink">{title}</p>
          <p className="mt-1 text-sm text-ink-muted">{text}</p>
        </div>
      </CardBody>
    </Card>
  );
}

export default async function DashboardPage() {
  const user = await getCurrentUser();
  const data = await api.get<DashboardSummary>("/dashboard/summary");
  const { kpis } = data;

  return (
    <>
      <PageHeader
        title="لوحة التحكم"
        description={`مرحبًا ${user.full_name} · آخر تحديث ${formatDateTime(data.generated_at)}`}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="العربيات النشطة" value={kpis.active_vehicles} icon={Bus} />
        <Kpi label="السائقون النشطون" value={kpis.active_drivers} icon={UsersRound} />
        <Kpi label="الورديات النشطة" value={kpis.active_shifts} icon={Clock} accent />
        <Kpi label="ورديات اليوم" value={kpis.today_shifts} icon={CalendarDays} />
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Placeholder
          icon={MapPin}
          title="الخريطة المباشرة"
          text="سيتم تفعيل التتبع المباشر في مرحلة GPS"
        />
        <Placeholder
          icon={Bell}
          title="التنبيهات التشغيلية"
          text="سيتم تفعيلها بعد تشغيل نظام التتبع والتحليل"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader
              title="التشغيل الجاري"
              description="الورديات النشطة الآن والتشغيل الحالي لكل منها"
            />
            {data.active_shifts.length === 0 ? (
              <EmptyState title="لا توجد ورديات نشطة الآن" />
            ) : (
              <Table>
                <THead>
                  <tr>
                    <TH>السائق</TH>
                    <TH>المركبة</TH>
                    <TH>التشغيل الحالي</TH>
                    <TH>منذ</TH>
                  </tr>
                </THead>
                <tbody>
                  {data.active_shifts.map((s) => (
                    <TR key={s.id}>
                      <TD>
                        <Link
                          href={`/shifts/${s.id}`}
                          className="font-semibold text-forest-700 hover:underline"
                        >
                          {s.driver.full_name}
                        </Link>
                      </TD>
                      <TD className="ltr-nums">{s.vehicle.internal_code}</TD>
                      <TD>
                        {s.active_session ? (
                          <>
                            {s.active_session.operation_type.name_ar}
                            {s.active_session.route ? (
                              <span className="text-ink-muted">
                                {" "}
                                — {s.active_session.route.name}
                              </span>
                            ) : null}
                          </>
                        ) : (
                          <span className="text-ink-muted">لم يحدد</span>
                        )}
                      </TD>
                      <TD className="text-ink-muted">{formatDuration(s.duration_minutes)}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="المركبات النشطة" />
            {data.vehicles.length === 0 ? (
              <EmptyState title="لا توجد مركبات نشطة" />
            ) : (
              <Table>
                <THead>
                  <tr>
                    <TH>المركبة</TH>
                    <TH>النوع</TH>
                    <TH>السائق</TH>
                    <TH>الحالة</TH>
                  </tr>
                </THead>
                <tbody>
                  {data.vehicles.map((v) => (
                    <TR key={v.id}>
                      <TD>
                        <Link
                          href={`/vehicles/${v.id}`}
                          className="font-semibold text-forest-700 hover:underline"
                        >
                          <span className="ltr-nums">{v.internal_code}</span>
                        </Link>
                        <span className="ms-2 text-xs text-ink-muted">{v.plate_number}</span>
                      </TD>
                      <TD>{v.vehicle_type}</TD>
                      <TD>{v.driver_name ?? <span className="text-ink-muted">بدون تكليف</span>}</TD>
                      <TD>
                        {v.in_shift ? (
                          <Badge tone="active">
                            في وردية{v.current_operation ? ` · ${v.current_operation}` : ""}
                          </Badge>
                        ) : (
                          <Badge>متوقفة</Badge>
                        )}
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader title="تكليفات السائقين الحالية" />
            {data.assignments.length === 0 ? (
              <EmptyState title="لا توجد تكليفات حالية" />
            ) : (
              <ul className="divide-y divide-line">
                {data.assignments.map((a) => (
                  <li
                    key={a.id}
                    className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm"
                  >
                    <span>
                      <Link
                        href={`/drivers/${a.driver_id}`}
                        className="font-medium hover:underline"
                      >
                        {a.driver_name}
                      </Link>
                      <span className="text-ink-muted"> ← </span>
                      <Link href={`/vehicles/${a.vehicle_id}`} className="ltr-nums hover:underline">
                        {a.vehicle_code}
                      </Link>
                    </span>
                    <Badge tone={a.role === "PRIMARY" ? "active" : "info"}>
                      {a.role === "PRIMARY" ? "أساسي" : "بديل"}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="رخص وتأمينات تحتاج متابعة" />
            {data.expiring_documents.length === 0 ? (
              <p className="px-5 py-4 text-sm text-ink-muted">
                لا توجد مستندات منتهية أو قريبة الانتهاء.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {data.expiring_documents.map((d) => (
                  <li
                    key={`${d.kind}-${d.entity_id}`}
                    className="flex items-start justify-between gap-3 px-5 py-3 text-sm"
                  >
                    <div>
                      <Link
                        href={`/${d.entity_type === "vehicle" ? "vehicles" : "drivers"}/${d.entity_id}`}
                        className="font-medium hover:underline"
                      >
                        {d.label}
                      </Link>
                      <p className="text-xs text-ink-muted">{DOC_LABELS[d.kind]}</p>
                    </div>
                    <ExpiryBadge status={d.status} date={d.expires_on} />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader title="آخر النشاطات" />
            {data.recent_activity.length === 0 ? (
              <p className="px-5 py-4 text-sm text-ink-muted">لا توجد نشاطات بعد.</p>
            ) : (
              <ol className="divide-y divide-line">
                {data.recent_activity.map((a) => {
                  const base = a.entity_type ? ENTITY_PATHS[a.entity_type] : undefined;
                  const label = actionLabel(a.action);
                  return (
                    <li key={a.id} className="px-5 py-3 text-sm">
                      {base && a.entity_id ? (
                        <Link
                          href={`${base}/${a.entity_id}`}
                          className="font-medium hover:underline"
                        >
                          {label}
                        </Link>
                      ) : (
                        <span className="font-medium">{label}</span>
                      )}
                      <p className="text-xs text-ink-muted">
                        {formatDateTime(a.occurred_at)}
                        {a.actor_name ? ` · ${a.actor_name}` : ""}
                      </p>
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
