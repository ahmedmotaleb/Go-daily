import type { Metadata } from "next";
import Link from "next/link";
import { voidImportAction } from "@/app/(app)/finance/ride-hailing/import/actions";
import { DetailRow, Stat } from "@/components/finance/filters";
import { ActionForm } from "@/components/forms/action-form";
import { TextareaField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import type { ImportBatch } from "@/lib/finance-types";
import { formatDateTime, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "استيراد كشوف" };

const SKIP_LABEL: Record<string, string> = { ERROR: "خطأ", DUPLICATE: "مكرر" };

export default async function ImportBatchPage({
  params,
  searchParams,
}: PageProps<"/finance/ride-hailing/imports/[id]">) {
  const me = await requirePermission("revenue:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const b = await api.get<ImportBatch>(`/ride-hailing/imports/${id}`);
  return (
    <>
      <PageHeader
        title={`استيراد ${b.file_name}`}
        description={`${b.platform.name} · ${formatDateTime(b.created_at)}`}
        breadcrumb={<Link href="/finance/ride-hailing/import">استيراد كشوف المنصات</Link>}
      />
      <Notice code={notice} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="صفوف الملف" value={formatNumber(b.rows_total)} />
        <Stat label="كشوف مسجلة" value={formatNumber(b.rows_imported)} />
        <Stat
          label="بانتظار المراجعة"
          value={formatNumber(b.pending)}
          tone={b.pending ? "warning" : undefined}
        />
        <Stat label="صفوف لم تُستورد" value={formatNumber(b.skipped.length)} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="الكشوف المسجلة" description="تُراجع وتُعتمد مثل أي كشف" />
          <CardBody>
            {b.statements.length === 0 ? (
              <EmptyState title="لا توجد كشوف" />
            ) : (
              <ul className="divide-y divide-line text-sm">
                {b.statements.map((s) => (
                  <li key={s.id} className="py-2">
                    <Link
                      href={`/finance/ride-hailing/${s.id}`}
                      className="text-primary hover:underline"
                    >
                      {s.name}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="صفوف لم تُستورد" />
          <CardBody>
            {b.skipped.length === 0 ? (
              <EmptyState title="كل الصفوف استوردت" />
            ) : (
              <dl className="divide-y divide-line">
                {b.skipped.map((s) => (
                  <DetailRow
                    key={s.row}
                    label={`صف ${s.row} — ${SKIP_LABEL[s.status] ?? s.status}`}
                  >
                    {s.messages.join("؛ ")}
                  </DetailRow>
                ))}
              </dl>
            )}
          </CardBody>
        </Card>
      </div>
      <Card className="mt-6 max-w-3xl">
        <CardHeader
          title="إلغاء الاستيراد"
          description="يُلغي كل كشف أنشأه هذا الملف (وإيراده إن كان معتمدًا). لا يُحذف شيء"
        />
        <CardBody>
          {b.status === "VOIDED" ? (
            <p className="text-sm">
              <Badge tone="neutral">ملغي</Badge>{" "}
              <span className="text-ink-muted">
                {formatDateTime(b.voided_at)} — {b.void_reason}
              </span>
            </p>
          ) : can(me, "revenue:approve") ? (
            <ActionForm
              action={voidImportAction.bind(null, b.id)}
              submitLabel="إلغاء الاستيراد"
              variant="danger"
              confirm="سيتم إلغاء كل الكشوف التي أنشأها هذا الملف. متابعة؟"
            >
              <TextareaField name="reason" label="السبب" rows={2} required />
            </ActionForm>
          ) : (
            <p className="text-sm text-ink-muted">الإلغاء يحتاج صلاحية اعتماد الإيرادات.</p>
          )}
        </CardBody>
      </Card>
    </>
  );
}
