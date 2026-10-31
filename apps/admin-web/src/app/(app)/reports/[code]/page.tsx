import { Download } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { FilterBar } from "@/components/finance/filters";
import { ReportTableView } from "@/components/reports/report-table";
import { Alert } from "@/components/ui/alert";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import type { ExpenseCategory, FuelType } from "@/lib/finance-types";
import { fleetOptions, type Option } from "@/lib/finance-refs";
import { formatNumber } from "@/lib/format";
import {
  FILTER_PARAM,
  REPORT_CODE,
  type Report,
  type ReportFilter,
  type ReportInfo,
} from "@/lib/report-types";
import { cairoToday, firstOfMonth, spDate, spUuid } from "@/lib/search";
import type { OperationType, Page, Route } from "@/lib/types";

export const metadata: Metadata = { title: "تقرير" };

const PREVIEW_ROWS = 500;

const FILTER_LABEL: Record<ReportFilter, string> = {
  vehicle: "المركبة",
  driver: "السائق",
  operation_type: "نوع التشغيل",
  route: "المسار",
  fuel_type: "نوع الوقود",
  category: "التصنيف",
};

async function filterOptions(
  filters: ReportFilter[],
): Promise<Partial<Record<ReportFilter, Option[]>>> {
  const want = new Set(filters);
  const [fleet, types, routes, fuel, categories] = await Promise.all([
    want.has("vehicle") || want.has("driver") ? fleetOptions() : null,
    want.has("operation_type") ? api.get<OperationType[]>("/operation-types") : null,
    want.has("route") ? api.get<Page<Route>>("/routes", { page_size: 100 }) : null,
    want.has("fuel_type") ? api.get<FuelType[]>("/fuel-types", { include_inactive: true }) : null,
    want.has("category")
      ? api.get<ExpenseCategory[]>("/expense-categories", { include_inactive: true })
      : null,
  ]);
  return {
    vehicle: fleet?.vehicles,
    driver: fleet?.drivers,
    operation_type: types?.map((t) => ({ value: t.id, label: t.name_ar })),
    route: routes?.items.map((r) => ({ value: r.id, label: r.name })),
    fuel_type: fuel?.map((t) => ({ value: t.id, label: t.name_ar })),
    category: categories?.map((c) => ({ value: c.id, label: c.name_ar })),
  };
}

export default async function ReportPage({ params, searchParams }: PageProps<"/reports/[code]">) {
  await requirePermission("reports:read");
  const { code } = await params;
  if (!REPORT_CODE.test(code)) notFound();
  const sp = await searchParams;
  const catalog = await api.get<ReportInfo[]>("/reports");
  const info = catalog.find((r) => r.code === code);
  if (!info) notFound();

  const query: Record<string, string | undefined> = {
    date_from: spDate(sp, "date_from") ?? firstOfMonth(),
    date_to: spDate(sp, "date_to") ?? cairoToday(),
  };
  for (const f of info.filters) query[FILTER_PARAM[f]] = spUuid(sp, FILTER_PARAM[f]);
  const [report, options] = await Promise.all([
    api.get<Report>(`/reports/${code}`, query),
    filterOptions(info.filters),
  ]);
  const csvQuery = new URLSearchParams(
    Object.entries(query).filter((e): e is [string, string] => Boolean(e[1])),
  ).toString();

  return (
    <>
      <PageHeader
        title={report.title}
        description={info.description}
        breadcrumb={<Link href="/reports">التقارير</Link>}
        actions={
          <a
            href={`/reports/${code}/csv?${csvQuery}`}
            className="inline-flex items-center gap-2 rounded-[var(--radius-control)] bg-forest-700 px-4 py-2 text-sm font-semibold text-white hover:bg-forest-800"
          >
            <Download className="size-4" aria-hidden="true" />
            تنزيل CSV
          </a>
        }
      />
      <Card className="mb-6">
        <FilterBar
          basePath={`/reports/${code}`}
          values={query}
          fields={[
            { type: "date", name: "date_from", label: "من" },
            { type: "date", name: "date_to", label: "إلى" },
            ...info.filters.map((f) => ({
              type: "select" as const,
              name: FILTER_PARAM[f],
              label: FILTER_LABEL[f],
              options: options[f] ?? [],
            })),
          ]}
        />
        {report.rows.length === 0 ? (
          <EmptyState title="لا توجد سجلات في هذه الفترة" />
        ) : (
          <>
            {report.rows.length > PREVIEW_ROWS ? (
              <Alert tone="info" className="m-4">
                يُعرض أول {formatNumber(PREVIEW_ROWS)} سجل من {formatNumber(report.rows.length)}.
                الإجمالي محسوب على كل السجلات، وملف CSV يحتوي الكل.
              </Alert>
            ) : null}
            <ReportTableView table={report} limit={PREVIEW_ROWS} />
          </>
        )}
      </Card>
      {report.summaries
        .filter((s) => s.rows.length > 0)
        .map((s) => (
          <Card key={s.title} className="mb-6">
            <CardHeader title={s.title} />
            <ReportTableView table={s} />
          </Card>
        ))}
      {report.notes.length ? (
        <Card>
          <CardHeader title="أساس الحساب" />
          <CardBody>
            <ul className="list-inside list-disc space-y-1 text-sm text-ink-muted">
              {report.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
