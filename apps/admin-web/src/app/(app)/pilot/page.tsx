import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField } from "@/components/forms/fields";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { DayPicker } from "@/components/vehicles/day-picker";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { egp } from "@/lib/cash";
import { fleetOptions } from "@/lib/finance-refs";
import { formatNumber } from "@/lib/format";
import { cairoToday, spDate } from "@/lib/search";
import type { PilotCheckState, PilotDay, PilotVerdict } from "@/lib/types";
import { addPilotAction, removePilotAction } from "./actions";

export const metadata: Metadata = { title: "التجربة الميدانية" };

const TIME = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const VERDICT_TONE: Record<PilotVerdict, "success" | "danger" | "warning"> = {
  COMPLETE: "success",
  INCOMPLETE: "danger",
  NEEDS_REVIEW: "warning",
};

const CHECK: Record<
  PilotCheckState,
  { label: string; tone: "success" | "danger" | "warning" | "neutral" }
> = {
  OK: { label: "مكتمل", tone: "success" },
  MISSING: { label: "ناقص", tone: "danger" },
  REVIEW: { label: "مراجعة", tone: "warning" },
  NOT_APPLICABLE: { label: "لا ينطبق", tone: "neutral" },
};

const GPS_GRADE: Record<string, string> = {
  EXCELLENT: "ممتازة",
  GOOD: "جيدة",
  NEEDS_REVIEW: "تحتاج مراجعة",
  INSUFFICIENT: "غير كافية",
};

const TRACKING: Record<string, string> = {
  ONLINE: "يتم التتبع",
  STALE: "الموقع لم يتحدث",
  OFFLINE: "انقطاع GPS",
};

function Figure({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-ink-muted">{label}</span>
      <span className="text-sm font-semibold">{value}</span>
    </div>
  );
}

function VehicleDay({ d, canManage }: { d: PilotDay; canManage: boolean }) {
  const gpsKm = d.shifts.reduce((s, x) => s + x.gps_km, 0);
  const odoKm = d.shifts.reduce((s, x) => s + (x.odometer_km ?? 0), 0);
  const loops = d.shifts.reduce((s, x) => s + x.loops, 0);
  const legs = d.shifts.reduce((s, x) => s + x.legs, 0);
  return (
    <Card>
      <CardHeader
        title={`${d.plate_number} · ${d.vehicle_code}`}
        description={
          d.drivers.length ? d.drivers.join("، ") : d.day_off ? "يوم إجازة" : "لا توجد وردية"
        }
        actions={
          <Badge tone={VERDICT_TONE[d.verdict]} dot>
            {d.verdict_ar}
          </Badge>
        }
      />
      <CardBody className="space-y-5">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Figure
            label="التتبع الآن"
            value={
              d.tracking_state ? (TRACKING[d.tracking_state] ?? d.tracking_state) : "خارج الوردية"
            }
          />
          <Figure
            label="المسافة GPS · العداد"
            value={`${formatNumber(gpsKm.toFixed(1))} · ${formatNumber(odoKm)} كم`}
          />
          <Figure
            label="دورات · اتجاهات"
            value={`${formatNumber(loops)} · ${formatNumber(legs)}`}
          />
          <Figure label="الإيراد" value={egp(d.revenue)} />
          <Figure label="الوقود" value={egp(d.fuel)} />
          <Figure label="المصروفات" value={egp(d.expenses)} />
          <Figure
            label="صافي التقفيل · المُسلّم"
            value={`${egp(d.closeout_net)} · ${egp(d.collected)}`}
          />
          <Figure label="المتبقي مع السائق" value={egp(d.remaining)} />
        </div>

        {d.shifts.length ? (
          <ul className="divide-y divide-line rounded-[var(--radius-control)] border border-line">
            {d.shifts.map((s) => (
              <li
                key={s.shift_id}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3.5 py-2.5 text-sm"
              >
                <Link href={`/shifts/${s.shift_id}`} className="font-semibold hover:underline">
                  {s.driver_name}
                </Link>
                <span className="ltr-nums text-ink-soft">
                  {s.started_at ? TIME.format(new Date(s.started_at)) : "—"} –{" "}
                  {s.ended_at ? TIME.format(new Date(s.ended_at)) : "مستمرة"}
                </span>
                <span className="text-ink-soft">
                  {s.operations.join("، ") || "لم يُحدد التشغيل"}
                </span>
                <span className="text-ink-muted">
                  جودة GPS: {GPS_GRADE[s.gps_grade] ?? s.gps_grade}
                </span>
              </li>
            ))}
          </ul>
        ) : null}

        <div>
          <h3 className="mb-2 text-sm font-bold">تقفيل اليوم</h3>
          <ul className="divide-y divide-line rounded-[var(--radius-control)] border border-line">
            {d.checks.map((c) => (
              <li key={c.code} className="flex items-center gap-3 px-3.5 py-2.5">
                <span className="flex-1 text-sm">
                  <span className="font-semibold">{c.label}</span>
                  <span className="block text-xs text-ink-soft">{c.detail}</span>
                </span>
                <Badge tone={CHECK[c.state].tone}>{CHECK[c.state].label}</Badge>
              </li>
            ))}
          </ul>
        </div>

        {d.open_cases.length ? (
          <div className="space-y-1">
            <h3 className="text-sm font-bold">حالات المراجعة المفتوحة</h3>
            {d.open_cases.map((c) => (
              <Link
                key={c.id}
                href={`/exceptions/${c.id}`}
                className="block text-sm text-primary hover:underline"
              >
                {c.summary}
              </Link>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-4">
          <Link
            href={`/vehicles/${d.vehicle_id}?day=${d.day}`}
            className="text-sm font-semibold text-primary hover:underline"
          >
            يوم السيارة بالتفصيل ←
          </Link>
          {canManage ? (
            <ActionForm
              action={removePilotAction.bind(null, d.vehicle_id)}
              submitLabel="إزالة من التجربة"
              variant="secondary"
              confirm="إزالة هذه السيارة من التجربة؟ لا تُحذف أي بيانات."
            />
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

export default async function PilotPage({ searchParams }: PageProps<"/pilot">) {
  const me = await requirePermission("tracking:read");
  if (!can(me, "revenue:read") || !can(me, "cash:read")) redirect("/forbidden");
  const sp = await searchParams;
  const day = spDate(sp, "day") ?? cairoToday();
  const canManage = can(me, "vehicles:write");
  const [cards, fleet] = await Promise.all([
    api.get<PilotDay[]>("/pilot", { day }),
    canManage ? fleetOptions() : null,
  ]);
  const inPilot = new Set(cards.map((c) => c.vehicle_id));
  const options = fleet?.vehicles.filter((v) => !inPilot.has(v.value)) ?? [];
  const counts = cards.reduce<Record<string, number>>((acc, c) => {
    acc[c.verdict] = (acc[c.verdict] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <PageHeader
        title="التجربة الميدانية"
        description="سيارات التجربة يومًا بيوم: التشغيل والتتبع والمال وتقفيل اليوم."
        actions={<DayPicker value={day} basePath="/pilot" />}
      />
      <Alert tone="info" className="mb-4">
        كل الأرقام من السجلات الفعلية. «بيانات ناقصة» تعني أن شيئًا لم يُسجل أو لم يُرسل بعد،
        و«يحتاج مراجعة» تعني أن هناك ما ينتظر اعتماد الإدارة أو حالة مفتوحة — وليس اتهامًا لأحد.
      </Alert>
      {cards.length ? (
        <ul className="mb-4 flex flex-wrap gap-4 text-sm text-ink-soft" aria-label="ملخص">
          <li>
            <strong className="text-success">{formatNumber(counts.COMPLETE ?? 0)}</strong> اليوم
            مكتمل
          </li>
          <li>
            <strong className="text-danger">{formatNumber(counts.INCOMPLETE ?? 0)}</strong> بيانات
            ناقصة
          </li>
          <li>
            <strong className="text-warning">{formatNumber(counts.NEEDS_REVIEW ?? 0)}</strong> يحتاج
            مراجعة
          </li>
        </ul>
      ) : null}
      <div className="space-y-6">
        {cards.length === 0 ? (
          <EmptyState
            title="لا توجد سيارات في التجربة"
            description="أضف سيارة خط ثابت أو مدارس وسيارة نقل ذكي لمتابعتهما هنا."
          />
        ) : (
          cards.map((d) => <VehicleDay key={d.vehicle_id} d={d} canManage={canManage} />)
        )}
        {canManage ? (
          <Card>
            <CardHeader
              title="إضافة سيارة للتجربة"
              description="الإضافة والإزالة تُسجل في سجل التغييرات."
            />
            <CardBody>
              <ActionForm action={addPilotAction} submitLabel="إضافة">
                <SelectField
                  name="vehicle_id"
                  label="السيارة"
                  placeholder="اختر السيارة"
                  options={options}
                  required
                />
              </ActionForm>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </>
  );
}
