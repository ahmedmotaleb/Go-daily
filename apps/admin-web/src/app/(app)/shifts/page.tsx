import { SHIFT_STATUS_LABELS_AR } from "@go-daily/shared";
import clsx from "clsx";
import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { formatDuration, ShiftStatusBadge } from "@/components/domain/shift-badges";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Page, Shift, ShiftStatus } from "@/lib/types";

export const metadata: Metadata = { title: "الورديات" };

const STATUSES = Object.keys(SHIFT_STATUS_LABELS_AR) as ShiftStatus[];

export default async function ShiftsPage({ searchParams }: PageProps<"/shifts">) {
  const me = await requirePermission("shifts:read");
  const sp = await searchParams;
  const status =
    typeof sp.status === "string" && (STATUSES as string[]).includes(sp.status)
      ? (sp.status as ShiftStatus)
      : undefined;
  const day = typeof sp.day === "string" && /^\d{4}-\d{2}-\d{2}$/.test(sp.day) ? sp.day : undefined;
  const page = Math.max(1, Number(sp.page) || 1);
  const data = await api.get<Page<Shift>>("/shifts", { status, day, page, page_size: 25 });

  const tab = (s?: ShiftStatus) => {
    const params = new URLSearchParams();
    if (s) params.set("status", s);
    if (day) params.set("day", day);
    const qs = params.toString();
    return qs ? `/shifts?${qs}` : "/shifts";
  };

  return (
    <>
      <PageHeader
        title="الورديات"
        description="تخطيط وبدء وإنهاء ورديات العمل وعمليات التشغيل داخلها"
        actions={
          can(me, "shifts:write") ? (
            <ButtonLink href="/shifts/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              وردية جديدة
            </ButtonLink>
          ) : null
        }
      />
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-4 py-3">
          <nav aria-label="حالة الوردية" className="flex flex-wrap gap-1">
            {[undefined, ...STATUSES].map((s) => (
              <Link
                key={s ?? "all"}
                href={tab(s)}
                aria-current={status === s ? "page" : undefined}
                className={clsx(
                  "rounded-full px-3 py-1.5 text-sm",
                  status === s ? "bg-forest-800 text-white" : "text-ink-muted hover:bg-neutral-100",
                )}
              >
                {s ? SHIFT_STATUS_LABELS_AR[s] : "الكل"}
              </Link>
            ))}
          </nav>
          <form className="flex items-end gap-2">
            {status ? <input type="hidden" name="status" value={status} /> : null}
            <label htmlFor="day" className="sr-only">
              اليوم
            </label>
            <Input id="day" name="day" type="date" defaultValue={day} className="w-44" />
            <Button type="submit" variant="secondary">
              عرض اليوم
            </Button>
          </form>
        </div>
        {data.items.length === 0 ? (
          <EmptyState title="لا توجد ورديات مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>السائق</TH>
                <TH>المركبة</TH>
                <TH>الحالة</TH>
                <TH>البداية</TH>
                <TH>النهاية</TH>
                <TH>التشغيل الحالي</TH>
                <TH>المسافة (عداد)</TH>
                <TH>المدة</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((s) => (
                <TR key={s.id}>
                  <TD>
                    <Link
                      href={`/shifts/${s.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {s.driver.full_name}
                    </Link>
                  </TD>
                  <TD>
                    <span className="ltr-nums">{s.vehicle.internal_code}</span>
                  </TD>
                  <TD>
                    <ShiftStatusBadge status={s.status} />
                  </TD>
                  <TD className="text-ink-muted">
                    {formatDateTime(s.started_at ?? s.planned_start_at)}
                  </TD>
                  <TD className="text-ink-muted">{formatDateTime(s.ended_at)}</TD>
                  <TD>
                    {s.active_session
                      ? `${s.active_session.operation_type.name_ar}${s.active_session.route ? ` — ${s.active_session.route.name}` : ""}`
                      : "—"}
                  </TD>
                  <TD className="ltr-nums">
                    {s.odometer_distance_km === null
                      ? "—"
                      : `${formatNumber(s.odometer_distance_km)} كم`}
                  </TD>
                  <TD>{formatDuration(s.duration_minutes)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
        <Pagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          basePath="/shifts"
          params={{ status, day }}
        />
      </Card>
    </>
  );
}
