import type { Metadata } from "next";
import Link from "next/link";
import { StatementImport } from "@/components/finance/statement-import";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import type { ImportBatch, Platform } from "@/lib/finance-types";
import { formatDateTime, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "استيراد كشوف المنصات" };

/** U19: CSV statements exported by the platform, checked before anything is saved. */
export default async function StatementImportPage() {
  await requirePermission("revenue:write");
  const [platforms, batches] = await Promise.all([
    api.get<Platform[]>("/ride-hailing/platforms"),
    api.get<ImportBatch[]>("/ride-hailing/imports"),
  ]);
  return (
    <>
      <PageHeader
        title="استيراد كشوف المنصات"
        description="من ملف CSV صدّرته المنصة. لا يتم سحب أي بيانات من المنصات؛ الربط المباشر يحتاج واجهة رسمية معتمدة"
        breadcrumb={<Link href="/finance/ride-hailing">النقل الذكي</Link>}
      />
      <Card className="mb-6">
        <CardBody>
          <StatementImport platforms={platforms.map((p) => ({ value: p.id, label: p.name }))} />
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="عمليات الاستيراد" />
        {batches.length === 0 ? (
          <EmptyState title="لم يتم استيراد ملفات بعد" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المنصة</TH>
                <TH>الملف</TH>
                <TH>الصفوف</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {batches.map((b) => (
                <TR key={b.id}>
                  <TD>
                    <Link
                      href={`/finance/ride-hailing/imports/${b.id}`}
                      className="font-semibold text-primary hover:underline"
                    >
                      {formatDateTime(b.created_at)}
                    </Link>
                  </TD>
                  <TD>{b.platform.name}</TD>
                  <TD className="ltr-nums">{b.file_name}</TD>
                  <TD className="ltr-nums">
                    {formatNumber(b.rows_imported)} / {formatNumber(b.rows_total)}
                  </TD>
                  <TD>
                    {b.status === "VOIDED" ? (
                      <Badge tone="neutral">ملغي</Badge>
                    ) : (
                      <Badge tone="success">مستورد</Badge>
                    )}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
