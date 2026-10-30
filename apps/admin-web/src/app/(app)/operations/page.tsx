import { TRIP_PATTERN_LABELS_AR } from "@go-daily/shared";
import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { ActiveBadge } from "@/components/domain/badges";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import type { OperationType, Page, Route } from "@/lib/types";

export const metadata: Metadata = { title: "التشغيل" };

export default async function OperationsPage({ searchParams }: PageProps<"/operations">) {
  const me = await requirePermission("operations:read");
  const sp = await searchParams;
  const q = typeof sp.q === "string" && sp.q ? sp.q : undefined;
  const type = typeof sp.type === "string" && sp.type ? sp.type : undefined;
  const page = Math.max(1, Number(sp.page) || 1);
  const [types, routes] = await Promise.all([
    api.get<OperationType[]>("/operation-types"),
    api.get<Page<Route>>("/routes", { q, operation_type_id: type, page, page_size: 25 }),
  ]);

  return (
    <>
      <PageHeader
        title="التشغيل"
        description="أنواع التشغيل ومسارات الخطوط الثابتة والمدارس ونقل الموظفين"
        actions={
          <>
            <ButtonLink href="/operations/school-runs">دورات المدارس</ButtonLink>
            {can(me, "tracking:read") ? (
              <ButtonLink href="/tracking">الخريطة المباشرة</ButtonLink>
            ) : null}
            {can(me, "operations:write") ? (
              <ButtonLink href="/operations/routes/new" variant="accent">
                <Plus className="size-4" aria-hidden="true" />
                مسار جديد
              </ButtonLink>
            ) : null}
          </>
        }
      />
      <Card className="mb-6">
        <CardHeader
          title="أنواع التشغيل"
          description="يمكن للمركبة تنفيذ أكثر من نوع تشغيل في نفس اليوم"
        />
        <ul className="flex flex-wrap gap-2 px-5 py-4">
          {types.map((t) => (
            <li key={t.id}>
              <Badge tone={t.uses_routes ? "active" : "neutral"}>
                {t.name_ar}
                {t.uses_routes ? " · بمسار" : ""}
              </Badge>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="المسارات" />
        <form
          className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3"
          role="search"
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="q" className="sr-only">
              بحث
            </label>
            <Input id="q" name="q" placeholder="بحث باسم المسار" defaultValue={q} />
          </div>
          <div>
            <label htmlFor="type" className="sr-only">
              النوع
            </label>
            <Select id="type" name="type" defaultValue={type ?? ""}>
              <option value="">كل الأنواع</option>
              {types
                .filter((t) => t.uses_routes)
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name_ar}
                  </option>
                ))}
            </Select>
          </div>
          <Button type="submit" variant="secondary">
            تطبيق
          </Button>
        </form>
        {routes.items.length === 0 ? (
          <EmptyState
            title="لا توجد مسارات"
            description="أضف مسارات الخطوط الثابتة (مثل موقف ⇄ جامعة) ودورات المدارس."
          />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>المسار</TH>
                <TH>النوع</TH>
                <TH>النقاط</TH>
                <TH>النمط</TH>
                <TH>الإحداثيات</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {routes.items.map((r) => {
                const withCoords = r.stops.filter((s) => s.latitude !== null).length;
                return (
                  <TR key={r.id}>
                    <TD>
                      <Link
                        href={`/operations/routes/${r.id}`}
                        className="font-semibold text-forest-700 hover:underline"
                      >
                        {r.name}
                      </Link>
                    </TD>
                    <TD>{r.operation_type.name_ar}</TD>
                    <TD className="text-sm">{r.stops.map((s) => s.name).join(" ← ")}</TD>
                    <TD>{TRIP_PATTERN_LABELS_AR[r.trip_pattern]}</TD>
                    <TD>
                      {withCoords === r.stops.length ? (
                        <Badge tone="success">مكتملة</Badge>
                      ) : (
                        <Badge tone="warning">
                          {withCoords}/{r.stops.length}
                        </Badge>
                      )}
                    </TD>
                    <TD>
                      <ActiveBadge active={r.is_active} />
                    </TD>
                  </TR>
                );
              })}
            </tbody>
          </Table>
        )}
        <Pagination
          page={routes.page}
          pageSize={routes.page_size}
          total={routes.total}
          basePath="/operations"
          params={{ q, type }}
        />
      </Card>
    </>
  );
}
