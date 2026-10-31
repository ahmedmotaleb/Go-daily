import type { Metadata } from "next";
import Link from "next/link";
import { saveFuelAction } from "@/app/(app)/finance/actions";
import { DetailRow } from "@/components/finance/filters";
import { FuelForm } from "@/components/finance/fuel-form";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { ReviewPanel } from "@/components/finance/review";
import { Notice } from "@/components/notice";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import {
  PAID_BY_LABELS,
  PAYMENT_METHOD_LABELS,
  UNIT_LABELS,
  FUEL_CATEGORY_LABELS,
} from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { FuelTx, FuelType } from "@/lib/finance-types";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "سجل وقود" };

export default async function FuelDetailPage({
  params,
  searchParams,
}: PageProps<"/finance/fuel/[id]">) {
  const me = await requirePermission("fuel:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const tx = await api.get<FuelTx>(`/fuel/${id}`);
  const canEdit = can(me, "fuel:write") && (tx.status === "SUBMITTED" || tx.status === "REJECTED");
  const canReview = can(me, "expenses:approve");
  const needsForm = canEdit || (canReview && tx.status === "APPROVED");
  const [types, fleet] = needsForm
    ? await Promise.all([api.get<FuelType[]>("/fuel-types"), fleetOptions()])
    : [[], { vehicles: [], drivers: [] }];
  const typeOptions = types.map((t) => ({ value: t.id, label: t.name_ar }));

  return (
    <>
      <PageHeader
        title={`${tx.fuel_type.name_ar} — ${tx.vehicle.name}`}
        description={formatDateTime(tx.occurred_at)}
        breadcrumb={<Link href="/finance/fuel">الوقود والزيوت</Link>}
      />
      <Notice code={notice} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="التفاصيل" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="المركبة">
                <Link href={`/vehicles/${tx.vehicle.id}`} className="ltr-nums hover:underline">
                  {tx.vehicle.name}
                </Link>
              </DetailRow>
              <DetailRow label="السائق">
                {tx.driver ? (
                  <Link href={`/drivers/${tx.driver.id}`} className="hover:underline">
                    {tx.driver.name}
                  </Link>
                ) : (
                  "—"
                )}
              </DetailRow>
              {tx.shift_id ? (
                <DetailRow label="الوردية">
                  <Link href={`/shifts/${tx.shift_id}`} className="text-forest-700 hover:underline">
                    عرض الوردية
                  </Link>
                </DetailRow>
              ) : null}
              <DetailRow label="النوع">
                {tx.fuel_type.name_ar} ({FUEL_CATEGORY_LABELS[tx.fuel_type.category]})
              </DetailRow>
              <DetailRow label="الكمية">
                <span className="ltr-nums">
                  {formatNumber(tx.quantity)} {UNIT_LABELS[tx.unit]}
                </span>
              </DetailRow>
              <DetailRow label="سعر الوحدة">
                <span className="ltr-nums">{formatMoney(tx.effective_unit_price)}</span>
              </DetailRow>
              <DetailRow label="الإجمالي">
                <span className="ltr-nums text-base font-bold">{formatMoney(tx.total_amount)}</span>
              </DetailRow>
              <DetailRow label="قراءة العداد">
                {tx.odometer_km === null ? "—" : `${formatNumber(tx.odometer_km)} كم`}
              </DetailRow>
              <DetailRow label="المحطة / المورد">{tx.vendor ?? "—"}</DetailRow>
              <DetailRow label="الدفع">
                {PAYMENT_METHOD_LABELS[tx.payment_method]} · {PAID_BY_LABELS[tx.paid_by]}
              </DetailRow>
              {tx.latitude !== null && tx.longitude !== null ? (
                <DetailRow label="الموقع عند الإدخال">
                  <span className="ltr-nums">
                    {tx.latitude.toFixed(5)}, {tx.longitude.toFixed(5)}
                    {tx.location_accuracy_m ? ` (±${Math.round(tx.location_accuracy_m)} م)` : ""}
                  </span>
                </DetailRow>
              ) : null}
              {tx.notes ? <DetailRow label="ملاحظات">{tx.notes}</DetailRow> : null}
            </dl>
          </CardBody>
        </Card>
        <ReviewPanel resource="fuel" record={tx} canReview={canReview} />
      </div>
      <div className="mt-6">
        <AttachmentsPanel
          ownerType="fuel_transaction"
          ownerId={tx.id}
          returnPath={`/finance/fuel/${tx.id}`}
          canWrite={can(me, "fuel:write")}
          locked={tx.status === "APPROVED" || tx.status === "VOIDED"}
          title="صورة الإيصال والمرفقات"
        />
      </div>
      {canEdit ? (
        <Card className="mt-6">
          <CardHeader title="تعديل السجل" description="التعديل متاح قبل الاعتماد فقط" />
          <CardBody>
            <FuelForm
              action={saveFuelAction.bind(null, "edit", tx.id)}
              mode="edit"
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              fuelTypes={typeOptions}
              record={tx}
              canApprove={false}
            />
          </CardBody>
        </Card>
      ) : null}
      {canReview && tx.status === "APPROVED" ? (
        <Card className="mt-6">
          <CardHeader
            title="تصحيح سجل معتمد"
            description="يُلغى هذا السجل وينشأ سجل جديد مرتبط به؛ يبقى الاثنان في السجل"
          />
          <CardBody>
            <FuelForm
              action={saveFuelAction.bind(null, "correct", tx.id)}
              mode="correct"
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              fuelTypes={typeOptions}
              record={tx}
              canApprove
            />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
