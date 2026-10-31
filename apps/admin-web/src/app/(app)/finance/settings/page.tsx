import type { Metadata } from "next";
import { createSettingAction, toggleSettingAction } from "@/app/(app)/finance/actions";
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

export const metadata: Metadata = { title: "إعدادات المالية" };

function Toggle({
  kind,
  id,
  active,
}: {
  kind: "platforms" | "fuel-types" | "expense-categories";
  id: string;
  active: boolean;
}) {
  return (
    <ActionForm
      action={toggleSettingAction.bind(null, kind, id, !active)}
      submitLabel={active ? "إيقاف" : "تفعيل"}
      variant="ghost"
      className="space-y-0"
    />
  );
}

function ListRow({
  title,
  meta,
  active,
  toggle,
}: {
  title: string;
  meta: string;
  active: boolean;
  toggle: React.ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
      <span>
        <span className="font-medium">{title}</span>
        <span className="ms-2 text-xs text-ink-muted">{meta}</span>
        {active ? null : <Badge className="ms-2">موقوف</Badge>}
      </span>
      {toggle}
    </li>
  );
}

export default async function FinanceSettingsPage({
  searchParams,
}: PageProps<"/finance/settings">) {
  await requirePermission("settings:manage");
  const { notice } = await searchParams;
  const [platforms, fuelTypes, categories] = await Promise.all([
    api.get<Platform[]>("/ride-hailing/platforms", { include_inactive: true }),
    api.get<FuelType[]>("/fuel-types", { include_inactive: true }),
    api.get<ExpenseCategory[]>("/expense-categories", { include_inactive: true }),
  ]);
  return (
    <>
      <PageHeader
        title="إعدادات المالية"
        description="الأنواع لا تُحذف حتى لا تتأثر السجلات القديمة؛ أوقف ما لا تحتاجه"
      />
      <Notice code={notice} />
      <div className="grid gap-6 xl:grid-cols-3">
        <Card>
          <CardHeader title="منصات النقل الذكي" />
          <CardBody>
            <ul className="divide-y divide-line">
              {platforms.map((p) => (
                <ListRow
                  key={p.id}
                  title={p.name}
                  meta=""
                  active={p.is_active}
                  toggle={<Toggle kind="platforms" id={p.id} active={p.is_active} />}
                />
              ))}
            </ul>
            <ActionForm
              action={createSettingAction.bind(null, "platforms")}
              submitLabel="إضافة منصة"
              variant="secondary"
              className="mt-4 border-t border-line pt-4"
            >
              <TextField name="name" label="اسم المنصة" required />
            </ActionForm>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="أنواع الوقود والزيوت" />
          <CardBody>
            <ul className="divide-y divide-line">
              {fuelTypes.map((t) => (
                <ListRow
                  key={t.id}
                  title={t.name_ar}
                  meta={`${t.code} · ${FUEL_CATEGORY_LABELS[t.category]} · ${UNIT_LABELS[t.default_unit]}`}
                  active={t.is_active}
                  toggle={<Toggle kind="fuel-types" id={t.id} active={t.is_active} />}
                />
              ))}
            </ul>
            <ActionForm
              action={createSettingAction.bind(null, "fuel-types")}
              submitLabel="إضافة نوع"
              variant="secondary"
              className="mt-4 border-t border-line pt-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <TextField name="code" label="الرمز (إنجليزي)" required />
                <TextField name="name_ar" label="الاسم" required />
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
            </ActionForm>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="تصنيفات المصروفات" />
          <CardBody>
            <ul className="divide-y divide-line">
              {categories.map((c) => (
                <ListRow
                  key={c.id}
                  title={c.name_ar}
                  meta={`${c.code} · ${EXPENSE_GROUP_LABELS[c.pnl_group]}`}
                  active={c.is_active}
                  toggle={<Toggle kind="expense-categories" id={c.id} active={c.is_active} />}
                />
              ))}
            </ul>
            <ActionForm
              action={createSettingAction.bind(null, "expense-categories")}
              submitLabel="إضافة تصنيف"
              variant="secondary"
              className="mt-4 border-t border-line pt-4"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <TextField name="code" label="الرمز (إنجليزي)" required />
                <TextField name="name_ar" label="الاسم" required />
                <SelectField
                  name="pnl_group"
                  label="مجموعة الربحية"
                  options={options(EXPENSE_GROUP_LABELS)}
                  required
                />
              </div>
            </ActionForm>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
