import { FileBarChart } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import type { ReportInfo } from "@/lib/report-types";

export const metadata: Metadata = { title: "التقارير" };

export default async function ReportsPage() {
  await requirePermission("reports:read");
  const reports = await api.get<ReportInfo[]>("/reports");
  return (
    <>
      <PageHeader
        title="التقارير"
        description="كل إجمالي في التقارير مجموع للسجلات المعروضة تحته، ويمكن تنزيله كملف CSV يفتح في Excel."
      />
      {reports.length === 0 ? (
        <EmptyState title="لا توجد تقارير متاحة لصلاحياتك" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {reports.map((r) => (
            <Link key={r.code} href={`/reports/${r.code}`} className="group">
              <Card className="h-full transition-colors group-hover:border-forest-500">
                <CardBody className="flex items-start gap-3">
                  <FileBarChart
                    className="mt-0.5 size-5 shrink-0 text-forest-700"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="font-semibold text-ink group-hover:text-forest-700">{r.title}</p>
                    <p className="mt-1 text-sm text-ink-muted">{r.description}</p>
                  </div>
                </CardBody>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
