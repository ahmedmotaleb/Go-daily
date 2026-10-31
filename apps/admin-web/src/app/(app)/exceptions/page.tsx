import type { Metadata } from "next";
import Link from "next/link";
import { FilterBar, Stat } from "@/components/finance/filters";
import { ActionForm } from "@/components/forms/action-form";
import { Notice } from "@/components/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import {
  LABEL_AR,
  SEVERITY_AR,
  SEVERITY_TONE,
  STATUS_AR,
  STATUS_TONE,
} from "@/lib/exception-labels";
import type { ExceptionRules, ExceptionSummary, OperationalException } from "@/lib/exception-types";
import { options } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import { formatDateTime, formatNumber } from "@/lib/format";
import { spDate, spEnum, spPage, spString, spUuid } from "@/lib/search";
import type { Page } from "@/lib/types";
import { runDetectionAction } from "./actions";

export const metadata: Metadata = { title: "حالات للمراجعة" };

const STATUS_FILTER = {
  ACTIVE: "تحتاج متابعة",
  ...STATUS_AR,
} as const;

export default async function ExceptionsPage({ searchParams }: PageProps<"/exceptions">) {
  const me = await requirePermission("exceptions:read");
  const sp = await searchParams;
  const filters = {
    // Default view: what still needs someone's attention.
    status:
      spEnum(sp, "status", Object.keys(STATUS_FILTER) as (keyof typeof STATUS_FILTER)[]) ??
      "ACTIVE",
    severity: spEnum(sp, "severity", ["HIGH", "MEDIUM", "LOW"] as const),
    rule_code: spString(sp, "rule_code"),
    vehicle_id: spUuid(sp, "vehicle_id"),
    driver_id: spUuid(sp, "driver_id"),
    date_from: spDate(sp, "date_from"),
    date_to: spDate(sp, "date_to"),
  };
  const page = spPage(sp);
  const [list, summary, meta, fleet] = await Promise.all([
    api.get<Page<OperationalException>>("/exceptions", { ...filters, page, page_size: 25 }),
    api.get<ExceptionSummary>("/exceptions/summary"),
    api.get<ExceptionRules>("/exceptions/rules"),
    fleetOptions(),
  ]);
  const run = meta.last_run;
  const runErrors = run ? Object.keys(run.errors) : [];

  return (
    <>
      <PageHeader
        title="حالات للمراجعة"
        description="إشارات من قواعد واضحة على بيانات التشغيل والمصروفات. كل حالة سبب للمراجعة وليست حكمًا على أحد."
      />
      <Notice code={typeof sp.notice === "string" ? sp.notice : undefined} />
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        <Stat label="تحتاج متابعة" value={formatNumber(summary.active)} />
        <Stat
          label="أهمية عالية"
          value={formatNumber(summary.by_severity.HIGH)}
          tone={summary.by_severity.HIGH ? "danger" : undefined}
        />
        <Stat label="قيد المراجعة" value={formatNumber(summary.by_status.UNDER_REVIEW ?? 0)} />
        <Stat
          label="مُصعّدة"
          value={formatNumber(summary.by_status.ESCALATED ?? 0)}
          tone={summary.by_status.ESCALATED ? "warning" : undefined}
        />
      </div>

      <Card className="mb-6">
        <CardHeader
          title="آخر فحص"
          description={
            run
              ? `${formatDateTime(run.started_at)} · من ${formatDateTime(run.window_start)} إلى ${formatDateTime(run.window_end)}`
              : "لم يتم تشغيل الفحص بعد"
          }
        />
        <CardBody className="space-y-3">
          {runErrors.length ? (
            <p className="text-sm text-danger">قواعد لم تعمل في آخر فحص: {runErrors.join("، ")}</p>
          ) : null}
          <p className="text-sm text-ink-muted">
            يعمل الفحص تلقائيًا حسب جدول الخادم، ويمكن تشغيله الآن. إعادة التشغيل لا تكرر الحالات.
          </p>
          {can(me, "exceptions:review") ? (
            <ActionForm
              action={runDetectionAction}
              submitLabel="تشغيل الفحص الآن"
              variant="secondary"
            >
              <label className="flex items-center gap-2 text-sm">
                آخر
                <select
                  name="days"
                  defaultValue="3"
                  className="h-9 rounded-md border border-line bg-surface px-2"
                >
                  {[1, 3, 7, 14, 31].map((d) => (
                    <option key={d} value={d}>
                      {formatNumber(d)}
                    </option>
                  ))}
                </select>
                يوم
              </label>
            </ActionForm>
          ) : null}
          <details className="text-sm">
            <summary className="cursor-pointer font-medium text-forest-700">
              القواعد المستخدمة
            </summary>
            <ul className="mt-2 space-y-1.5">
              {meta.rules.map((r) => (
                <li key={r.code}>
                  <span className="font-semibold">{r.title_ar}</span>
                  {r.enabled ? "" : " (معطلة)"} —{" "}
                  <span className="text-ink-muted">{r.description_ar}</span>
                </li>
              ))}
            </ul>
          </details>
        </CardBody>
      </Card>

      <Card>
        <FilterBar
          basePath="/exceptions"
          values={filters}
          fields={[
            { type: "select", name: "status", label: "الحالة", options: options(STATUS_FILTER) },
            { type: "select", name: "severity", label: "الأهمية", options: options(SEVERITY_AR) },
            {
              type: "select",
              name: "rule_code",
              label: "القاعدة",
              options: meta.rules.map((r) => ({ value: r.code, label: r.title_ar })),
            },
            { type: "select", name: "vehicle_id", label: "المركبة", options: fleet.vehicles },
            { type: "select", name: "driver_id", label: "السائق", options: fleet.drivers },
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
          ]}
        />
        {list.items.length === 0 ? (
          <EmptyState title="لا توجد حالات مطابقة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>الوقت</TH>
                <TH>الحالة</TH>
                <TH>الوصف</TH>
                <TH>المركبة</TH>
                <TH>السائق</TH>
                <TH>الأهمية</TH>
                <TH>المتابعة</TH>
              </tr>
            </THead>
            <tbody>
              {list.items.map((e) => (
                <TR key={e.id}>
                  <TD className="ltr-nums whitespace-nowrap">{formatDateTime(e.occurred_at)}</TD>
                  <TD>
                    <Badge tone={e.label === "REVIEW_REQUIRED" ? "warning" : "info"}>
                      {LABEL_AR[e.label]}
                    </Badge>
                  </TD>
                  <TD>
                    <Link
                      href={`/exceptions/${e.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {e.rule_title}
                    </Link>
                    <p className="text-xs text-ink-muted">{e.summary}</p>
                  </TD>
                  <TD className="ltr-nums whitespace-nowrap">{e.vehicle?.name ?? "—"}</TD>
                  <TD>{e.driver?.name ?? "—"}</TD>
                  <TD>
                    <Badge tone={SEVERITY_TONE[e.severity]}>{SEVERITY_AR[e.severity]}</Badge>
                  </TD>
                  <TD>
                    <Badge tone={STATUS_TONE[e.status]}>{STATUS_AR[e.status]}</Badge>
                    {e.cleared_at ? (
                      <p className="mt-1 text-xs text-ink-muted">لم تعد تظهر في آخر فحص</p>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
        <Pagination
          page={list.page}
          pageSize={list.page_size}
          total={list.total}
          basePath="/exceptions"
          params={filters}
        />
      </Card>
    </>
  );
}
