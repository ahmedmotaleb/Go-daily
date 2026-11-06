import { saveScheduleAction } from "@/app/(app)/finance/actions";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { DueItem, MaintenanceType } from "@/lib/maintenance-types";
import { formatNumber } from "@/lib/format";
import { DueTable } from "./due";

function defaults(t: MaintenanceType) {
  const parts = [
    t.interval_km ? `${formatNumber(t.interval_km)} كم` : null,
    t.interval_days ? `${formatNumber(t.interval_days)} يوم` : null,
  ].filter(Boolean);
  return parts.length ? `${t.name_ar} (كل ${parts.join(" أو ")})` : t.name_ar;
}

/** Maintenance schedules of one vehicle, with an add/update form. */
export async function VehicleSchedulesPanel({
  vehicleId,
  canWrite,
}: {
  vehicleId: string;
  canWrite: boolean;
}) {
  const [rows, types] = await Promise.all([
    api.get<DueItem[]>("/maintenance/due", { vehicle_id: vehicleId, include_inactive: true }),
    canWrite ? api.get<MaintenanceType[]>("/maintenance/types") : Promise.resolve([]),
  ]);
  return (
    <Card>
      <CardHeader
        title="جدول الصيانة"
        description="الموعد التالي يُحسب من آخر صيانة معتمدة، أو من نقطة البداية إن لم توجد"
      />
      {rows.length === 0 ? (
        <EmptyState title="لا توجد جداول صيانة لهذه المركبة" />
      ) : (
        <DueTable rows={rows} showVehicle={false} />
      )}
      {canWrite ? (
        <CardBody className="border-t border-line">
          <h3 className="mb-3 text-sm font-semibold">إضافة جدول أو تعديله</h3>
          <ActionForm action={saveScheduleAction.bind(null, vehicleId)} submitLabel="حفظ الجدول">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <SelectField
                name="type_id"
                label="نوع الصيانة"
                options={types.map((t) => ({ value: t.id, label: defaults(t) }))}
                placeholder="اختر النوع"
                required
              />
              <TextField
                name="interval_km"
                label="كل (كم)"
                inputMode="numeric"
                hint="اتركه فارغًا لاستخدام القيمة الافتراضية للنوع"
              />
              <TextField
                name="interval_days"
                label="كل (يوم)"
                inputMode="numeric"
                hint="اتركه فارغًا لاستخدام القيمة الافتراضية للنوع"
              />
              <TextField
                name="baseline_km"
                label="آخر تنفيذ معروف (كم)"
                inputMode="numeric"
                hint="عند عدم وجود سجل صيانة في النظام"
              />
              <TextField name="baseline_date" label="تاريخ آخر تنفيذ معروف" type="date" />
              <SelectField
                name="is_active"
                label="الحالة"
                options={[
                  { value: "true", label: "مفعل" },
                  { value: "false", label: "موقوف" },
                ]}
                defaultValue="true"
              />
            </div>
          </ActionForm>
        </CardBody>
      ) : null}
    </Card>
  );
}
