import type { Metadata } from "next";
import Link from "next/link";
import { saveStationAction, toggleStationAction } from "@/app/(app)/finance/stations/actions";
import { DetailRow, Stat } from "@/components/finance/filters";
import { RecordStatusBadge } from "@/components/finance/review";
import { StationForm } from "@/components/finance/station-form";
import { ActionForm } from "@/components/forms/action-form";
import { Notice } from "@/components/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { UNIT_LABELS } from "@/lib/finance-labels";
import type { FuelStationDetail, FuelType } from "@/lib/finance-types";
import { formatDateTime, formatMoney, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "محطة وقود" };

function price(value: string | null) {
  return value === null ? "—" : `${formatNumber(value)} ج.م`;
}

function difference(pct: string | null) {
  if (pct === null) return "—";
  const n = Number(pct);
  if (n === 0) return "مثل متوسط الأسطول";
  return `${n > 0 ? "أعلى" : "أقل"} من متوسط الأسطول بـ ${formatNumber(Math.abs(n))}%`;
}

export default async function StationPage({
  params,
  searchParams,
}: PageProps<"/finance/stations/[id]">) {
  const me = await requirePermission("fuel:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const manage = can(me, "settings:manage");
  const [station, types] = await Promise.all([
    api.get<FuelStationDetail>(`/fuel-stations/${id}`),
    manage ? api.get<FuelType[]>("/fuel-types") : Promise.resolve([]),
  ]);
  return (
    <>
      <PageHeader
        title={station.name}
        description={[station.brand, station.address].filter(Boolean).join(" · ") || undefined}
        breadcrumb={<Link href="/finance/stations">محطات الوقود</Link>}
        actions={
          manage ? (
            <ActionForm
              action={toggleStationAction.bind(null, station.id, !station.is_active)}
              submitLabel={station.is_active ? "إيقاف المحطة" : "تفعيل المحطة"}
              variant="ghost"
              className="space-y-0"
            />
          ) : null
        }
      />
      <Notice code={notice} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="مشتريات مسجلة" value={formatNumber(station.transactions_count)} />
        <Stat
          label="بانتظار المراجعة"
          value={formatNumber(station.pending_count)}
          tone={station.pending_count ? "warning" : undefined}
          hint="غير محسوبة في الأسعار"
        />
        <Stat label="بإيصال مرفق" value={formatNumber(station.receipts_count)} />
        <Stat label="آخر شراء" value={formatDateTime(station.last_purchase_at)} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="بيانات المحطة" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="الحالة">
                {station.is_active ? "مفعلة" : <Badge>موقوفة</Badge>}
                {station.is_trusted ? (
                  <Badge tone="success" className="ms-2">
                    موثوقة
                  </Badge>
                ) : null}
              </DetailRow>
              <DetailRow label="الأنواع">
                {station.fuel_types.map((t) => t.name_ar).join("، ") || "—"}
              </DetailRow>
              <DetailRow label="الموقع">
                {station.latitude !== null && station.longitude !== null ? (
                  <span className="ltr-nums">
                    {station.latitude.toFixed(5)}, {station.longitude.toFixed(5)} ·{" "}
                    {formatNumber(station.radius_m)} م
                  </span>
                ) : (
                  "غير محدد"
                )}
              </DetailRow>
              {station.notes ? <DetailRow label="ملاحظات">{station.notes}</DetailRow> : null}
            </dl>
          </CardBody>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader
            title="الأسعار"
            description="من المشتريات المعتمدة فقط؛ الفرق عن متوسط الأسطول رقم للاطلاع وليس حكمًا"
          />
          {station.prices.length === 0 ? (
            <EmptyState title="لا توجد مشتريات معتمدة بعد" />
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>النوع</TH>
                  <TH>المشتريات</TH>
                  <TH>متوسط السعر</TH>
                  <TH>أقل / أعلى</TH>
                  <TH>آخر سعر</TH>
                  <TH>مقارنة بالأسطول</TH>
                </tr>
              </THead>
              <tbody>
                {station.prices.map((p) => (
                  <TR key={`${p.fuel_type.id}-${p.unit}`}>
                    <TD>
                      {p.fuel_type.name_ar}
                      <span className="block text-xs text-ink-muted">
                        لكل {UNIT_LABELS[p.unit]}
                      </span>
                    </TD>
                    <TD className="ltr-nums">
                      {formatNumber(p.count)} · {formatMoney(p.total_amount)}
                    </TD>
                    <TD className="ltr-nums font-medium">{price(p.average_price)}</TD>
                    <TD className="ltr-nums">
                      {price(p.min_price)} / {price(p.max_price)}
                    </TD>
                    <TD className="ltr-nums">{price(p.last_price)}</TD>
                    <TD className="text-sm">
                      {difference(p.difference_pct)}
                      <span className="ltr-nums block text-xs text-ink-muted">
                        {price(p.fleet_average_price)}
                      </span>
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
      {station.monthly.length ? (
        <Card className="mt-6">
          <CardHeader title="متوسط السعر شهريًا" />
          <Table>
            <THead>
              <tr>
                <TH>الشهر</TH>
                <TH>النوع</TH>
                <TH>متوسط السعر</TH>
                <TH>المشتريات</TH>
              </tr>
            </THead>
            <tbody>
              {station.monthly.map((m) => (
                <TR key={`${m.month}-${m.fuel_type}`}>
                  <TD className="ltr-nums">{m.month.slice(0, 7)}</TD>
                  <TD>{m.fuel_type}</TD>
                  <TD className="ltr-nums">{price(m.average_price)}</TD>
                  <TD className="ltr-nums">{formatNumber(m.count)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
      <Card className="mt-6">
        <CardHeader title="آخر المشتريات" />
        {station.recent.length === 0 ? (
          <EmptyState title="لا توجد مشتريات مرتبطة بهذه المحطة" />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>التاريخ</TH>
                <TH>المركبة</TH>
                <TH>النوع</TH>
                <TH>الكمية</TH>
                <TH>سعر الوحدة</TH>
                <TH>الإجمالي</TH>
                <TH>إيصال</TH>
                <TH>الحالة</TH>
              </tr>
            </THead>
            <tbody>
              {station.recent.map((t) => (
                <TR key={t.id}>
                  <TD>
                    <Link
                      href={`/finance/fuel/${t.id}`}
                      className="font-semibold text-primary hover:underline"
                    >
                      {formatDateTime(t.occurred_at)}
                    </Link>
                  </TD>
                  <TD>
                    <span className="ltr-nums">{t.vehicle.name}</span>
                    {t.driver ? (
                      <span className="block text-xs text-ink-muted">{t.driver.name}</span>
                    ) : null}
                  </TD>
                  <TD>{t.fuel_type}</TD>
                  <TD className="ltr-nums">{formatNumber(t.quantity)}</TD>
                  <TD className="ltr-nums">{price(t.unit_price)}</TD>
                  <TD className="ltr-nums">{formatMoney(t.total_amount)}</TD>
                  <TD>{t.has_receipt ? "نعم" : "—"}</TD>
                  <TD>
                    <RecordStatusBadge status={t.status} />
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {manage ? (
        <Card className="mt-6 max-w-4xl">
          <CardHeader title="تعديل المحطة" />
          <CardBody>
            <StationForm
              action={saveStationAction.bind(null, station.id)}
              fuelTypes={types}
              station={station}
            />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
