import { OWNERSHIP_LABELS_AR } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AttachmentsPanel } from "@/components/attachments/attachments-panel";
import { AuditTrail } from "@/components/audit-trail";
import { Notice } from "@/components/notice";
import { AssignmentHistory, AssignmentPanel } from "@/components/domain/assignments";
import { ActiveBadge, ExpiryBadge } from "@/components/domain/badges";
import { ActionForm } from "@/components/forms/action-form";
import { TextField } from "@/components/forms/fields";
import { VehicleSchedulesPanel } from "@/components/maintenance/schedules-panel";
import { Alert } from "@/components/ui/alert";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatNumber } from "@/lib/format";
import type { Assignment, Driver, Page, Vehicle, VehicleType } from "@/lib/types";
import { setVehicleActiveAction, updateVehicleAction } from "../actions";
import { VehicleForm } from "../vehicle-form";

export const metadata: Metadata = { title: "بيانات المركبة" };

export default async function VehicleDetailPage({
  params,
  searchParams,
}: PageProps<"/vehicles/[id]">) {
  const me = await requirePermission("vehicles:read");
  const { id } = await params;
  const sp = await searchParams;
  const vehicle = await api.get<Vehicle | null>(`/vehicles/${id}`, undefined, { allow404: true });
  if (!vehicle) notFound();

  const canEdit = can(me, "vehicles:write");
  const canAssign = can(me, "assignments:write");
  const [types, history, drivers] = await Promise.all([
    canEdit ? api.get<VehicleType[]>("/vehicle-types") : Promise.resolve([] as VehicleType[]),
    can(me, "assignments:read")
      ? api.get<Page<Assignment>>(`/vehicles/${id}/assignments`, { page_size: 50 })
      : Promise.resolve(null),
    canAssign && can(me, "drivers:read")
      ? api.get<Page<Driver>>("/drivers", { employment_status: "ACTIVE", page_size: 100 })
      : Promise.resolve(null),
  ]);

  const driverChoices = (drivers?.items ?? []).map((d) => ({
    value: d.id,
    label: d.current_assignments.length
      ? `${d.full_name} (مكلف: ${d.current_assignments.map((a) => a.vehicle_code).join("، ")})`
      : d.full_name,
  }));

  return (
    <>
      <PageHeader
        title={`${vehicle.internal_code} · ${vehicle.plate_number}`}
        breadcrumb={<Link href="/vehicles">الأسطول</Link>}
        description={[
          vehicle.vehicle_type.name_ar,
          vehicle.manufacturer,
          vehicle.model,
          vehicle.model_year,
        ]
          .filter(Boolean)
          .join(" · ")}
        actions={<ActiveBadge active={vehicle.is_active} />}
      />
      {sp.created === "1" ? (
        <Alert tone="success" className="mb-4">
          تمت إضافة المركبة.
        </Alert>
      ) : null}
      <Notice code={sp.notice} />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardBody>
            <p className="text-xs text-ink-muted">قراءة العداد</p>
            <p className="ltr-nums mt-1 text-xl font-bold">
              {formatNumber(vehicle.current_odometer_km)}{" "}
              <span className="text-sm font-normal">كم</span>
            </p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="mb-1 text-xs text-ink-muted">رخصة المركبة</p>
            <ExpiryBadge status={vehicle.license_status} date={vehicle.license_expiry} />
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="mb-1 text-xs text-ink-muted">التأمين</p>
            <ExpiryBadge status={vehicle.insurance_status} date={vehicle.insurance_expiry} />
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <p className="text-xs text-ink-muted">الملكية</p>
            <p className="mt-1 font-semibold">{OWNERSHIP_LABELS_AR[vehicle.ownership_status]}</p>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="بيانات المركبة" />
            <CardBody>
              {canEdit ? (
                <VehicleForm
                  action={updateVehicleAction.bind(null, vehicle.id)}
                  types={types}
                  vehicle={vehicle}
                />
              ) : (
                <p className="text-sm whitespace-pre-line text-ink-muted">
                  {vehicle.notes ?? "لا توجد ملاحظات."}
                </p>
              )}
            </CardBody>
          </Card>
          {history ? (
            <AssignmentHistory side="vehicle" items={history.items} total={history.total} />
          ) : null}
          {can(me, "maintenance:read") ? (
            <VehicleSchedulesPanel vehicleId={vehicle.id} canWrite={can(me, "maintenance:write")} />
          ) : null}
          <AttachmentsPanel
            ownerType="vehicle"
            ownerId={vehicle.id}
            returnPath={`/vehicles/${vehicle.id}`}
            canWrite={canEdit}
            locked={false}
            title="مستندات المركبة"
          />
        </div>
        <div className="space-y-6">
          {can(me, "assignments:read") ? (
            <AssignmentPanel
              side="vehicle"
              fixedId={vehicle.id}
              current={vehicle.current_assignments}
              choices={driverChoices}
              canWrite={canAssign}
              canAssign={vehicle.is_active}
              inactiveReason="لا يمكن التكليف على مركبة موقوفة."
            />
          ) : null}
          {canEdit ? (
            <Card>
              <CardHeader title="حالة المركبة" />
              <CardBody>
                <ActionForm
                  action={setVehicleActiveAction.bind(null, vehicle.id, !vehicle.is_active)}
                  submitLabel={vehicle.is_active ? "إيقاف المركبة" : "تفعيل المركبة"}
                  variant={vehicle.is_active ? "danger" : "primary"}
                  confirm={vehicle.is_active ? "إيقاف هذه المركبة عن التشغيل؟" : undefined}
                  version={vehicle.updated_at}
                >
                  <p className="text-sm text-ink-muted">
                    {vehicle.is_active
                      ? "المركبة الموقوفة لا تقبل تكليفات أو ورديات جديدة. لا يتم حذف أي بيانات."
                      : "إعادة المركبة للتشغيل."}
                  </p>
                  <TextField name="reason" label="السبب" />
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
          {can(me, "audit:read") ? <AuditTrail entityType="vehicle" entityId={vehicle.id} /> : null}
        </div>
      </div>
    </>
  );
}
