import { EMPLOYMENT_STATUS_LABELS_AR } from "@go-daily/shared";
import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { EmploymentBadge, ExpiryBadge } from "@/components/domain/badges";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import type { Driver, Page } from "@/lib/types";

export const metadata: Metadata = { title: "السائقون" };

const STATUSES = Object.keys(
  EMPLOYMENT_STATUS_LABELS_AR,
) as (keyof typeof EMPLOYMENT_STATUS_LABELS_AR)[];

export default async function DriversPage({ searchParams }: PageProps<"/drivers">) {
  const me = await requirePermission("drivers:read");
  const sp = await searchParams;
  const q = typeof sp.q === "string" && sp.q ? sp.q : undefined;
  const status =
    typeof sp.status === "string" && (STATUSES as string[]).includes(sp.status)
      ? sp.status
      : undefined;
  const license =
    sp.license === "expired" || sp.license === "expiring" || sp.license === "attention"
      ? sp.license
      : undefined;
  const page = Math.max(1, Number(sp.page) || 1);

  const data = await api.get<Page<Driver>>("/drivers", {
    q,
    employment_status: status,
    license,
    page,
    page_size: 25,
  });

  return (
    <>
      <PageHeader
        title="السائقون"
        description="بيانات السائقين والرخص والتكليف الحالي وحساب التطبيق"
        actions={
          can(me, "drivers:write") ? (
            <ButtonLink href="/drivers/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              سائق جديد
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
            <Input
              id="q"
              name="q"
              placeholder="بحث بالاسم أو الهاتف أو رقم الرخصة"
              defaultValue={q}
            />
          </div>
          <div>
            <label htmlFor="status" className="sr-only">
              حالة العمل
            </label>
            <Select id="status" name="status" defaultValue={status ?? ""}>
              <option value="">كل الحالات</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {EMPLOYMENT_STATUS_LABELS_AR[s]}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="license" className="sr-only">
              الرخصة
            </label>
            <Select id="license" name="license" defaultValue={license ?? ""}>
              <option value="">كل الرخص</option>
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
            title={q || status || license ? "لا يوجد سائقون مطابقون" : "لم تتم إضافة سائقين بعد"}
          />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>الاسم</TH>
                <TH>الهاتف</TH>
                <TH>رخصة القيادة</TH>
                <TH>المركبة الحالية</TH>
                <TH>حساب التطبيق</TH>
                <TH>حالة العمل</TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((d) => (
                <TR key={d.id}>
                  <TD>
                    <Link
                      href={`/drivers/${d.id}`}
                      className="font-semibold text-forest-700 hover:underline"
                    >
                      {d.full_name}
                    </Link>
                  </TD>
                  <TD className="ltr-nums">{d.phone}</TD>
                  <TD>
                    <div className="ltr-nums text-xs text-ink-muted">{d.license_number ?? "—"}</div>
                    <ExpiryBadge status={d.license_status} date={d.license_expiry} />
                  </TD>
                  <TD>
                    {d.current_assignments.length ? (
                      d.current_assignments.map((a) => (
                        <div key={a.id} className="ltr-nums">
                          {a.vehicle_code}
                        </div>
                      ))
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                  </TD>
                  <TD>
                    {d.user_id === null ? (
                      <span className="text-xs text-ink-muted">لا يوجد</span>
                    ) : d.app_account_active ? (
                      <Badge tone="success">مفعل</Badge>
                    ) : (
                      <Badge>موقوف</Badge>
                    )}
                  </TD>
                  <TD>
                    <EmploymentBadge status={d.employment_status} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
        <Pagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          basePath="/drivers"
          params={{ q, status, license }}
        />
      </Card>
    </>
  );
}
