import type { Metadata } from "next";
import Link from "next/link";
import { saveStationAction } from "@/app/(app)/finance/stations/actions";
import { StationForm } from "@/components/finance/station-form";
import { Notice } from "@/components/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import type { FuelStation, FuelType } from "@/lib/finance-types";
import { formatDate, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "محطات الوقود" };

export default async function StationsPage({ searchParams }: PageProps<"/finance/stations">) {
  const me = await requirePermission("fuel:read");
  const { notice } = await searchParams;
  const manage = can(me, "settings:manage");
  const [stations, types] = await Promise.all([
    api.get<FuelStation[]>("/fuel-stations", { include_inactive: true }),
    manage ? api.get<FuelType[]>("/fuel-types") : Promise.resolve([]),
  ]);
  return (
    <>
      <PageHeader
        title="محطات الوقود والموردون"
        description="اختيار المحطة اختياري؛ المحطة الجديدة غير المسجلة لا تمنع تسجيل الشراء"
      />
      <Notice code={notice} />
      <Card>
        {stations.length === 0 ? (
          <EmptyState title="لا توجد محطات مسجلة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>المحطة</TH>
                <TH>الأنواع</TH>
                <TH>المشتريات</TH>
                <TH>آخر شراء</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {stations.map((s) => (
                <TR key={s.id}>
                  <TD>
                    <Link
                      href={`/finance/stations/${s.id}`}
                      className="font-semibold text-primary hover:underline"
                    >
                      {s.name}
                    </Link>
                    {s.brand || s.address ? (
                      <span className="block text-xs text-ink-muted">
                        {[s.brand, s.address].filter(Boolean).join(" · ")}
                      </span>
                    ) : null}
                  </TD>
                  <TD>{s.fuel_types.map((t) => t.name_ar).join("، ") || "—"}</TD>
                  <TD className="ltr-nums">{formatNumber(s.transactions_count)}</TD>
                  <TD>{formatDate(s.last_purchase_at)}</TD>
                  <TD className="space-x-1 space-x-reverse">
                    {s.is_trusted ? <Badge tone="success">موثوقة</Badge> : null}
                    {s.is_active ? null : <Badge>موقوفة</Badge>}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {manage ? (
        <Card className="mt-6 max-w-4xl">
          <CardHeader title="إضافة محطة" />
          <CardBody>
            <StationForm action={saveStationAction.bind(null, null)} fuelTypes={types} />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
