import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { ActiveBadge, ExpiryBadge } from "@/components/domain/badges";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatNumber } from "@/lib/format";
import type { Page, Vehicle, VehicleType } from "@/lib/types";

export const metadata: Metadata = { title: "الأسطول" };

const one = (v: string | string[] | undefined) => (typeof v === "string" && v ? v : undefined);

export default async function VehiclesPage({ searchParams }: PageProps<"/vehicles">) {
  const me = await requirePermission("vehicles:read");
  const sp = await searchParams;
  const q = one(sp.q);
  const type = one(sp.type);
  const status = sp.status === "active" || sp.status === "inactive" ? sp.status : undefined;
  const expiry =
    sp.expiry === "expired" || sp.expiry === "expiring" || sp.expiry === "attention"
      ? sp.expiry
      : undefined;
  const page = Math.max(1, Number(sp.page) || 1);

  const [types, data] = await Promise.all([
    api.get<VehicleType[]>("/vehicle-types"),
    api.get<Page<Vehicle>>("/vehicles", {
      q,
      vehicle_type_id: type,
      is_active: status === undefined ? undefined : status === "active",
      expiry,
      page,
      page_size: 25,
    }),
  ]);

  return (
    <>
      <PageHeader
        title="الأسطول"
        description="المركبات وحالة الرخص والتأمين والسائق الحالي"
        actions={
          can(me, "vehicles:write") ? (
            <ButtonLink href="/vehicles/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              مركبة جديدة
            </ButtonLink>
          ) : null
        }
      />
      <Card>
        <form
          className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3"
          role="search"
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="q" className="sr-only">
              بحث
            </label>
            <Input id="q" name="q" placeholder="بحث بالكود أو اللوحة أو الموديل" defaultValue={q} />
          </div>
          <div>
            <label htmlFor="type" className="sr-only">
              النوع
            </label>
            <Select id="type" name="type" defaultValue={type ?? ""}>
              <option value="">كل الأنواع</option>
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name_ar}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="status" className="sr-only">
              الحالة
            </label>
            <Select id="status" name="status" defaultValue={status ?? ""}>
              <option value="">كل الحالات</option>
              <option value="active">نشطة</option>
              <option value="inactive">موقوفة</option>
            </Select>
          </div>
          <div>
            <label htmlFor="expiry" className="sr-only">
              الرخص والتأمين
            </label>
            <Select id="expiry" name="expiry" defaultValue={expiry ?? ""}>
              <option value="">كل الرخص والتأمين</option>
              <option value="attention">تحتاج متابعة</option>
              <option value="expiring">تنتهي قريبًا</option>
              <option value="expired">منتهية</option>
            </Select>
          </div>
          <Button type="submit" variant="secondary">
            تطبيق
          </Button>
        </form>
        {data.items.length === 0 ? (
          <EmptyState
            title={
              q || type || status || expiry ? "لا توجد مركبات مطابقة" : "لم تتم إضافة مركبات بعد"
            }
            description="أضف المركبات لبدء تسجيل التكليفات والورديات."
          />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>الكود</TH>
                <TH>اللوحة</TH>
                <TH>النوع والموديل</TH>
                <TH>السائق الحالي</TH>
                <TH>العداد (كم)</TH>
                <TH>الرخصة</TH>
                <TH>التأمين</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((v) => {
                const primary = v.current_assignments.find((a) => a.role === "PRIMARY");
                return (
                  <TR key={v.id}>
                    <TD>
                      <Link
                        href={`/vehicles/${v.id}`}
                        className="ltr-nums font-semibold text-forest-700 hover:underline"
                      >
                        {v.internal_code}
                      </Link>
                    </TD>
                    <TD className="font-medium">{v.plate_number}</TD>
                    <TD>
                      <div>{v.vehicle_type.name_ar}</div>
                      <div className="text-xs text-ink-muted">
                        {[v.manufacturer, v.model, v.model_year].filter(Boolean).join(" · ") || "—"}
                      </div>
                    </TD>
                    <TD>
                      {primary ? (
                        primary.driver_name
                      ) : (
                        <span className="text-ink-muted">بدون تكليف</span>
                      )}
                    </TD>
                    <TD className="ltr-nums">{formatNumber(v.current_odometer_km)}</TD>
                    <TD>
                      <ExpiryBadge status={v.license_status} date={v.license_expiry} />
                    </TD>
                    <TD>
                      <ExpiryBadge status={v.insurance_status} date={v.insurance_expiry} />
                    </TD>
                    <TD>
                      <ActiveBadge active={v.is_active} />
                    </TD>
                  </TR>
                );
              })}
            </tbody>
          </Table>
        )}
        <Pagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          basePath="/vehicles"
          params={{ q, type, status, expiry }}
        />
      </Card>
    </>
  );
}
