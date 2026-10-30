import type { Metadata } from "next";
import Link from "next/link";
import { saveMaintenanceAction } from "@/app/(app)/finance/actions";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { DetailRow } from "@/components/finance/filters";
import { ReviewPanel } from "@/components/finance/review";
import { MaintenanceForm } from "@/components/maintenance/maintenance-form";
import { Notice } from "@/components/notice";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { FuelTx } from "@/lib/finance-types";
import type { MaintenanceRecord, MaintenanceType } from "@/lib/maintenance-types";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import type { Page } from "@/lib/types";

export const metadata: Metadata = { title: "سجل صيانة" };

export default async function MaintenanceRecordPage({
  params,
  searchParams,
}: PageProps<"/maintenance/records/[id]">) {
  const me = await requirePermission("maintenance:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const r = await api.get<MaintenanceRecord>(`/maintenance/records/${id}`);
  const canWrite = can(me, "maintenance:write");
  const canEdit = canWrite && (r.status === "SUBMITTED" || r.status === "REJECTED");
  const canReview = can(me, "expenses:approve");
  const canCorrect = canReview && r.status === "APPROVED";
  const needsForm = canEdit || canCorrect;
  const [types, fleet, purchases] = needsForm
    ? await Promise.all([
        api.get<MaintenanceType[]>("/maintenance/types"),
        fleetOptions(),
        can(me, "fuel:read")
          ? api.get<Page<FuelTx>>("/fuel", {
              vehicle_id: r.vehicle.id,
              category: "CONSUMABLE",
              page_size: 30,
            })
          : Promise.resolve(null),
      ])
    : [[], { vehicles: [], drivers: [] }, null];
  const typeOptions = types.map((t) => ({ value: t.id, label: t.name_ar }));
  const oilOptions = (purchases?.items ?? [])
    .filter((p) => p.status !== "VOIDED")
    .map((p) => ({
      value: p.id,
      label: `${p.fuel_type.name_ar} · ${formatDateTime(p.occurred_at)} · ${formatMoney(p.total_amount)}`,
    }));

  return (
    <>
      <PageHeader
        title={`${r.type.name_ar} — ${r.vehicle.name}`}
        description={formatDate(r.performed_on)}
        breadcrumb={<Link href="/maintenance">الصيانة</Link>}
      />
      <Notice code={notice} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="التفاصيل" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="المركبة">
                <Link href={`/vehicles/${r.vehicle.id}`} className="ltr-nums hover:underline">
                  {r.vehicle.name}
                </Link>
              </DetailRow>
              <DetailRow label="قراءة العداد">
                {r.odometer_km === null ? "—" : `${formatNumber(r.odometer_km)} كم`}
              </DetailRow>
              <DetailRow label="الورشة / المورد">{r.vendor ?? "—"}</DetailRow>
              <DetailRow label="قطع الغيار">
                <span className="ltr-nums">{formatMoney(r.parts_cost)}</span>
              </DetailRow>
              <DetailRow label="المصنعية">
                <span className="ltr-nums">{formatMoney(r.labor_cost)}</span>
              </DetailRow>
              <DetailRow label="تكاليف أخرى">
                <span className="ltr-nums">{formatMoney(r.other_cost)}</span>
              </DetailRow>
              <DetailRow label="الإجمالي">
                <span className="ltr-nums text-base font-bold">{formatMoney(r.total_cost)}</span>
              </DetailRow>
              {r.downtime_start ? (
                <DetailRow label="توقف المركبة">
                  {formatDateTime(r.downtime_start)} — {formatDateTime(r.downtime_end)}
                  {r.downtime_hours !== null ? ` (${formatNumber(r.downtime_hours)} ساعة)` : ""}
                </DetailRow>
              ) : null}
              {r.fuel_transaction_id ? (
                <DetailRow label="شراء الزيت المرتبط">
                  <Link
                    href={`/finance/fuel/${r.fuel_transaction_id}`}
                    className="text-forest-700 hover:underline"
                  >
                    عرض سجل الشراء
                  </Link>
                </DetailRow>
              ) : null}
              {r.description ? (
                <DetailRow label="الأعمال المنفذة">{r.description}</DetailRow>
              ) : null}
              {r.notes ? <DetailRow label="ملاحظات">{r.notes}</DetailRow> : null}
            </dl>
          </CardBody>
        </Card>
        <ReviewPanel resource="maintenance" record={r} canReview={canReview} />
      </div>
      <div className="mt-6">
        <AttachmentsPanel
          ownerType="maintenance_record"
          ownerId={r.id}
          returnPath={`/maintenance/records/${r.id}`}
          canWrite={canWrite}
          locked={r.status === "APPROVED" || r.status === "VOIDED"}
          title="الفواتير والمرفقات"
        />
      </div>
      {canEdit ? (
        <Card className="mt-6">
          <CardHeader title="تعديل السجل" description="التعديل متاح قبل اعتماد التكلفة فقط" />
          <CardBody>
            <MaintenanceForm
              action={saveMaintenanceAction.bind(null, "edit", r.id)}
              mode="edit"
              vehicles={fleet.vehicles}
              types={typeOptions}
              oilPurchases={oilOptions}
              record={r}
              canApprove={false}
            />
          </CardBody>
        </Card>
      ) : null}
      {canCorrect ? (
        <Card className="mt-6">
          <CardHeader
            title="تصحيح سجل معتمد"
            description="يُلغى هذا السجل وينشأ سجل جديد مرتبط به"
          />
          <CardBody>
            <MaintenanceForm
              action={saveMaintenanceAction.bind(null, "correct", r.id)}
              mode="correct"
              vehicles={fleet.vehicles}
              types={typeOptions}
              oilPurchases={oilOptions}
              record={r}
              canApprove
            />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
