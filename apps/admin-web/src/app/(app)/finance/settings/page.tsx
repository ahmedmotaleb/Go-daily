import type { Metadata } from "next";
import Link from "next/link";
import {
  createSettingAction,
  editSettingAction,
  toggleSettingAction,
} from "@/app/(app)/finance/actions";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { Notice } from "@/components/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import {
  EXPENSE_GROUP_LABELS,
  FUEL_CATEGORY_LABELS,
  options,
  UNIT_LABELS,
} from "@/lib/finance-labels";
import type { ExpenseCategory, FuelType, Platform } from "@/lib/finance-types";
import { formatNumber } from "@/lib/format";
import type { MaintenanceType } from "@/lib/maintenance-types";
import type { OperationKind, OperationType, VehicleType } from "@/lib/types";

export const metadata: Metadata = { title: "البيانات الأساسية" };

type Kind =
  | "platforms"
  | "fuel-types"
  | "expense-categories"
  | "operation-types"
  | "vehicle-types"
  | "maintenance-types";

const OPERATION_KIND_LABELS: Record<OperationKind, string> = {
  FIXED_ROUTE: "خط ثابت",
  RIDE_HAILING: "نقل ذكي",
  SCHOOL_ROUTE: "دورة مدرسة",
  PRIVATE_TRIP: "رحلة خاصة",
  EMPLOYEE_TRANSPORT: "نقل موظفين",
  OTHER: "أخرى",
};

type Row = {
  id: string;
  title: string;
  meta: string;
  active: boolean;
  sort?: number;
  edit?: React.ReactNode;
};

function Toggle({ kind, id, active }: { kind: Kind; id: string; active: boolean }) {
  return (
    <ActionForm
      action={toggleSettingAction.bind(null, kind, id, !active)}
      submitLabel={active ? "إيقاف" : "تفعيل"}
      variant="ghost"
      className="space-y-0"
    />
  );
}

function MasterList({
  kind,
  title,
  description,
  rows,
  nameField = "name_ar",
  addLabel,
  add,
}: {
  kind: Kind;
  title: string;
  description?: string;
  rows: Row[];
  nameField?: "name_ar" | "name";
  addLabel: string;
  add: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardBody>
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <li key={r.id} className="py-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  <span className="font-medium">{r.title}</span>
                  {r.meta ? <span className="ms-2 text-xs text-ink-muted">{r.meta}</span> : null}
                  {r.active ? null : <Badge className="ms-2">موقوف</Badge>}
                </span>
                <Toggle kind={kind} id={r.id} active={r.active} />
              </div>
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-primary">تعديل</summary>
                <ActionForm
                  action={editSettingAction.bind(null, kind, r.id)}
                  submitLabel="حفظ"
                  variant="secondary"
                  className="mt-2 space-y-3"
                >
                  <div className="grid gap-3 sm:grid-cols-2">
                    <TextField name={nameField} label="الاسم" defaultValue={r.title} required />
                    {r.sort !== undefined ? (
                      <TextField
                        name="sort_order"
                        label="الترتيب"
                        inputMode="numeric"
                        defaultValue={r.sort}
                      />
                    ) : null}
                    {r.edit}
                  </div>
                </ActionForm>
              </details>
            </li>
          ))}
        </ul>
        <ActionForm
          action={createSettingAction.bind(null, kind)}
          submitLabel={addLabel}
          variant="secondary"
          className="mt-4 border-t border-line pt-4"
        >
          {add}
        </ActionForm>
      </CardBody>
    </Card>
  );
}

function intervals(t?: MaintenanceType) {
  return (
    <>
      <TextField
        name="interval_km"
        label="كل (كم)"
        inputMode="numeric"
        defaultValue={t?.interval_km ?? undefined}
      />
      <TextField
        name="interval_days"
        label="كل (يوم)"
        inputMode="numeric"
        defaultValue={t?.interval_days ?? undefined}
      />
    </>
  );
}

function consumable(choices: { value: string; label: string }[], t?: MaintenanceType) {
  return (
    <SelectField
      name="consumable_type_id"
      label="المستهلك الذي تستخدمه"
      options={choices}
      placeholder="لا شيء"
      defaultValue={t?.consumable_type_id ?? undefined}
      hint="مثل: تغيير الزيت يستخدم زيت الموتور"
    />
  );
}

function codeAndName() {
  return (
    <>
      <TextField name="code" label="الرمز (إنجليزي)" required />
      <TextField name="name_ar" label="الاسم" required />
    </>
  );
}

/** U48: one place for the lists everything else picks from. Nothing is deleted. */
export default async function MasterDataPage({ searchParams }: PageProps<"/finance/settings">) {
  await requirePermission("settings:manage");
  const { notice } = await searchParams;
  const all = { include_inactive: true };
  const [platforms, fuelTypes, categories, operationTypes, vehicleTypes, serviceTypes] =
    await Promise.all([
      api.get<Platform[]>("/ride-hailing/platforms", all),
      api.get<FuelType[]>("/fuel-types", all),
      api.get<ExpenseCategory[]>("/expense-categories", all),
      api.get<OperationType[]>("/operation-types", all),
      api.get<VehicleType[]>("/vehicle-types", all),
      api.get<MaintenanceType[]>("/maintenance/types", all),
    ]);
  const consumables = fuelTypes
    .filter((t) => t.category === "CONSUMABLE" && t.is_active)
    .map((t) => ({ value: t.id, label: t.name_ar }));
  const fuelName = Object.fromEntries(fuelTypes.map((t) => [t.id, t.name_ar]));

  return (
    <>
      <PageHeader
        title="البيانات الأساسية"
        description="القوائم التي تختار منها بقية الشاشات. لا يُحذف شيء حتى لا تتأثر السجلات القديمة؛ أوقف ما لا تحتاجه"
      />
      <Notice code={notice} />
      <Card className="mb-6">
        <CardBody className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <span className="text-ink-muted">قوائم لها صفحاتها:</span>
          <Link href="/operations" className="text-primary hover:underline">
            المسارات
          </Link>
          <Link href="/finance/stations" className="text-primary hover:underline">
            محطات الوقود والموردون
          </Link>
          <Link href="/policies" className="text-primary hover:underline">
            حدود المراجعة وقواعد التنبيهات
          </Link>
        </CardBody>
      </Card>
      <div className="grid gap-6 xl:grid-cols-2">
        <MasterList
          kind="operation-types"
          title="أنواع التشغيل"
          rows={operationTypes.map((t) => ({
            id: t.id,
            title: t.name_ar,
            meta: `${t.code} · ${OPERATION_KIND_LABELS[t.kind]}`,
            active: t.is_active,
            sort: t.sort_order,
          }))}
          addLabel="إضافة نوع تشغيل"
          add={
            <div className="grid gap-3 sm:grid-cols-3">
              {codeAndName()}
              <SelectField
                name="kind"
                label="الفئة"
                options={options(OPERATION_KIND_LABELS)}
                required
              />
            </div>
          }
        />
        <MasterList
          kind="vehicle-types"
          title="أنواع السيارات"
          rows={vehicleTypes.map((t) => ({
            id: t.id,
            title: t.name_ar,
            meta: t.code,
            active: t.is_active,
            sort: t.sort_order,
          }))}
          addLabel="إضافة نوع سيارة"
          add={<div className="grid gap-3 sm:grid-cols-2">{codeAndName()}</div>}
        />
        <MasterList
          kind="maintenance-types"
          title="أنواع الصيانة"
          description="الفترات الافتراضية؛ جدول كل سيارة يمكنه تغييرها"
          rows={serviceTypes.map((t) => ({
            id: t.id,
            title: t.name_ar,
            meta: [
              t.code,
              t.interval_km ? `كل ${formatNumber(t.interval_km)} كم` : null,
              t.interval_days ? `كل ${formatNumber(t.interval_days)} يوم` : null,
              t.consumable_type_id ? `يستخدم ${fuelName[t.consumable_type_id] ?? ""}` : null,
            ]
              .filter(Boolean)
              .join(" · "),
            active: t.is_active,
            sort: t.sort_order,
            edit: (
              <>
                {intervals(t)}
                {consumable(consumables, t)}
              </>
            ),
          }))}
          addLabel="إضافة نوع صيانة"
          add={
            <div className="grid gap-3 sm:grid-cols-2">
              {codeAndName()}
              {intervals()}
              {consumable(consumables)}
            </div>
          }
        />
        <MasterList
          kind="fuel-types"
          title="أنواع الوقود والزيوت"
          rows={fuelTypes.map((t) => ({
            id: t.id,
            title: t.name_ar,
            meta: `${t.code} · ${FUEL_CATEGORY_LABELS[t.category]} · ${UNIT_LABELS[t.default_unit]}`,
            active: t.is_active,
            sort: t.sort_order,
          }))}
          addLabel="إضافة نوع"
          add={
            <div className="grid gap-3 sm:grid-cols-2">
              {codeAndName()}
              <SelectField
                name="category"
                label="الفئة"
                options={options(FUEL_CATEGORY_LABELS)}
                required
              />
              <SelectField
                name="default_unit"
                label="الوحدة"
                options={options(UNIT_LABELS)}
                required
              />
            </div>
          }
        />
        <MasterList
          kind="expense-categories"
          title="تصنيفات المصروفات"
          rows={categories.map((c) => ({
            id: c.id,
            title: c.name_ar,
            meta: `${c.code} · ${EXPENSE_GROUP_LABELS[c.pnl_group]}`,
            active: c.is_active,
            sort: c.sort_order,
          }))}
          addLabel="إضافة تصنيف"
          add={
            <div className="grid gap-3 sm:grid-cols-2">
              {codeAndName()}
              <SelectField
                name="pnl_group"
                label="مجموعة الربحية"
                options={options(EXPENSE_GROUP_LABELS)}
                required
              />
            </div>
          }
        />
        <MasterList
          kind="platforms"
          title="منصات النقل الذكي"
          nameField="name"
          rows={platforms.map((p) => ({ id: p.id, title: p.name, meta: "", active: p.is_active }))}
          addLabel="إضافة منصة"
          add={<TextField name="name" label="اسم المنصة" required />}
        />
      </div>
    </>
  );
}
