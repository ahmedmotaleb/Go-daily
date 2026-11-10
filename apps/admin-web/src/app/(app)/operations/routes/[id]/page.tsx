import { TRIP_PATTERN_LABELS_AR, WEEKDAY_LABELS_AR, WEEKDAY_ORDER } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditTrail } from "@/components/audit-trail";
import { ActiveBadge } from "@/components/domain/badges";
import { RouteRevenueRates } from "@/components/domain/route-revenue-rates";
import { ActionForm } from "@/components/forms/action-form";
import { Notice } from "@/components/notice";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Route, RouteRevenueRate } from "@/lib/types";

/** U08: one immutable snapshot of the route definition. */
type RouteVersion = {
  version: number;
  effective_from: string;
  created_by: string | null;
  snapshot: {
    name: string;
    expected_distance_km: string | null;
    stops: {
      id: string;
      name: string;
      latitude: string | null;
      longitude: string | null;
      radius_m: number;
    }[];
  };
};
import { setRouteActiveAction, updateRouteAction } from "../../actions";
import { RouteForm } from "../route-form";

export const metadata: Metadata = { title: "المسار" };

export default async function RouteDetailPage({
  params,
  searchParams,
}: PageProps<"/operations/routes/[id]">) {
  const me = await requirePermission("operations:read");
  const { id } = await params;
  const sp = await searchParams;
  const route = await api.get<Route | null>(`/routes/${id}`, undefined, { allow404: true });
  if (!route) notFound();
  const canEdit = can(me, "operations:write");
  const [rates, versions] = await Promise.all([
    can(me, "revenue:read")
      ? api.get<RouteRevenueRate[]>(`/routes/${id}/revenue-rates`)
      : Promise.resolve(null),
    api.get<RouteVersion[]>(`/routes/${id}/versions`),
  ]);
  const days = route.operating_days?.length
    ? WEEKDAY_ORDER.filter((d) => route.operating_days?.includes(d))
        .map((d) => WEEKDAY_LABELS_AR[d])
        .join("، ")
    : "كل الأيام";

  return (
    <>
      <PageHeader
        title={route.name}
        breadcrumb={<Link href="/operations">التشغيل</Link>}
        description={`${route.operation_type.name_ar} · ${TRIP_PATTERN_LABELS_AR[route.trip_pattern]} · ${days}`}
        actions={<ActiveBadge active={route.is_active} />}
      />
      <Notice code={sp.notice} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader title="بيانات المسار" />
            <CardBody>
              {canEdit ? (
                <RouteForm
                  action={updateRouteAction.bind(null, route.id)}
                  types={[]}
                  route={route}
                />
              ) : (
                <ol className="space-y-2 text-sm">
                  {route.stops.map((s) => (
                    <li key={s.id}>
                      {s.sequence}. {s.name}{" "}
                      {s.latitude ? (
                        <span className="ltr-nums text-ink-muted">
                          ({s.latitude}, {s.longitude})
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </CardBody>
          </Card>
        </div>
        <div className="space-y-6">
          {canEdit ? (
            <Card>
              <CardHeader title="حالة المسار" />
              <CardBody>
                <ActionForm
                  action={setRouteActiveAction.bind(null, route.id, !route.is_active)}
                  submitLabel={route.is_active ? "إيقاف المسار" : "تفعيل المسار"}
                  variant={route.is_active ? "danger" : "primary"}
                  version={route.updated_at}
                >
                  <p className="text-sm text-ink-muted">
                    المسار الموقوف لا يظهر عند بدء تشغيل جديد. السجلات السابقة تبقى كما هي.
                  </p>
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}
          {rates ? (
            <RouteRevenueRates
              routeId={route.id}
              rates={rates}
              canWrite={can(me, "revenue:write")}
              roundTrip={route.trip_pattern === "ROUND_TRIP"}
            />
          ) : null}
          <Card>
            <CardHeader
              title="إصدارات المسار"
              description="كل تعديل يحفظ إصدارًا جديدًا؛ الدورات والاتجاهات السابقة تبقى مقاسة على الإصدار الذي كان ساريًا وقتها."
            />
            <ul className="divide-y divide-line">
              {versions.map((v) => (
                <li key={v.version} className="space-y-1 px-5 py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">الإصدار {formatNumber(v.version)}</span>
                    <span className="ltr-nums text-xs text-ink-soft">
                      من {formatDateTime(v.effective_from)}
                    </span>
                    {v.created_by ? (
                      <span className="text-xs text-ink-soft">· {v.created_by}</span>
                    ) : null}
                  </div>
                  <div className="text-xs text-ink-soft">
                    {v.snapshot.stops.map((s) => s.name).join(" ← ")}
                    {v.snapshot.expected_distance_km
                      ? ` · ${v.snapshot.expected_distance_km} كم`
                      : ""}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
          {can(me, "audit:read") ? <AuditTrail entityType="route" entityId={route.id} /> : null}
        </div>
      </div>
    </>
  );
}
