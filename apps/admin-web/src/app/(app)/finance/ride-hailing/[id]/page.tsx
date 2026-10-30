import type { Metadata } from "next";
import Link from "next/link";
import { saveStatementAction } from "@/app/(app)/finance/actions";
import { DetailRow } from "@/components/finance/filters";
import { ReviewPanel } from "@/components/finance/review";
import { StatementForm } from "@/components/finance/statement-form";
import { Notice } from "@/components/notice";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { RECEIVED_BY_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { Platform, Statement } from "@/lib/finance-types";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "كشف منصة" };

export default async function StatementDetailPage({
  params,
  searchParams,
}: PageProps<"/finance/ride-hailing/[id]">) {
  const me = await requirePermission("revenue:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const s = await api.get<Statement>(`/ride-hailing/statements/${id}`);
  const canEdit = can(me, "revenue:write") && (s.status === "SUBMITTED" || s.status === "REJECTED");
  const canReview = can(me, "revenue:approve");
  const canCorrect = canReview && s.status === "APPROVED";
  const [platforms, fleet] =
    canEdit || canCorrect
      ? await Promise.all([api.get<Platform[]>("/ride-hailing/platforms"), fleetOptions()])
      : [[], { vehicles: [], drivers: [] }];
  const platformOptions = platforms.map((p) => ({ value: p.id, label: p.name }));
  const payout = Number(s.platform_payout);

  return (
    <>
      <PageHeader
        title={`${s.platform.name} — ${s.driver.name}`}
        description={`${formatDate(s.period_start)} — ${formatDate(s.period_end)}`}
        breadcrumb={<Link href="/finance/ride-hailing">النقل الذكي</Link>}
      />
      <Notice code={notice} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="أرقام الكشف" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="المركبة">
                <span className="ltr-nums">{s.vehicle.name}</span>
              </DetailRow>
              <DetailRow label="عدد الرحلات">{formatNumber(s.trips_count)}</DetailRow>
              <DetailRow label="إجمالي الأجرة">
                <span className="ltr-nums">{formatMoney(s.gross_earnings)}</span>
              </DetailRow>
              <DetailRow label="إكراميات">
                <span className="ltr-nums">{formatMoney(s.tips)}</span>
              </DetailRow>
              <DetailRow label="حوافز / تسويات">
                <span className="ltr-nums">{formatMoney(s.adjustments)}</span>
              </DetailRow>
              <DetailRow label="إجمالي الدخل">
                <span className="ltr-nums font-bold">{formatMoney(s.income)}</span>
              </DetailRow>
              <DetailRow label="عمولة المنصة">
                <span className="ltr-nums">{formatMoney(s.platform_fees)}</span>
              </DetailRow>
              <DetailRow label="الصافي">
                <span className="ltr-nums text-base font-bold">{formatMoney(s.net_earnings)}</span>
              </DetailRow>
              <DetailRow label="نقدي لدى السائق">
                <span className="ltr-nums">{formatMoney(s.cash_collected)}</span>
              </DetailRow>
              <DetailRow label="تحويل المنصة">
                {payout >= 0 ? (
                  <span className="ltr-nums">
                    {formatMoney(s.platform_payout)} → {RECEIVED_BY_LABELS[s.payout_recipient]}
                  </span>
                ) : (
                  <span className="ltr-nums text-warning">
                    مستحق للمنصة {formatMoney(s.platform_payout.replace(/^-/, ""))}
                  </span>
                )}
              </DetailRow>
              {s.statement_reference ? (
                <DetailRow label="مرجع الكشف">{s.statement_reference}</DetailRow>
              ) : null}
              {s.revenue_entry_id ? (
                <DetailRow label="الإيراد الناتج">
                  <Link
                    href={`/finance/revenue/${s.revenue_entry_id}`}
                    className="text-forest-700 hover:underline"
                  >
                    عرض سجل الإيراد
                  </Link>
                </DetailRow>
              ) : null}
              {s.notes ? <DetailRow label="ملاحظات">{s.notes}</DetailRow> : null}
            </dl>
          </CardBody>
        </Card>
        <ReviewPanel resource="statements" record={s} canReview={canReview} />
      </div>
      {canEdit ? (
        <Card className="mt-6">
          <CardHeader title="تعديل الكشف" description="التعديل متاح قبل الاعتماد فقط" />
          <CardBody>
            <StatementForm
              action={saveStatementAction.bind(null, "edit", s.id)}
              mode="edit"
              platforms={platformOptions}
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              record={s}
              canApprove={false}
            />
          </CardBody>
        </Card>
      ) : null}
      {canCorrect ? (
        <Card className="mt-6">
          <CardHeader
            title="تصحيح كشف معتمد"
            description="يُلغى الكشف وإيراده ومقبوضاته، وينشأ كشف جديد مرتبط به"
          />
          <CardBody>
            <StatementForm
              action={saveStatementAction.bind(null, "correct", s.id)}
              mode="correct"
              platforms={platformOptions}
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              record={s}
              canApprove
            />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
