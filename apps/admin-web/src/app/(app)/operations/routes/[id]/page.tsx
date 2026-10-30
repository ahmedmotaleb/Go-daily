import { TRIP_PATTERN_LABELS_AR, WEEKDAY_LABELS_AR, WEEKDAY_ORDER } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditTrail } from "@/components/audit-trail";
import { ActiveBadge } from "@/components/domain/badges";
import { ActionForm } from "@/components/forms/action-form";
import { Notice } from "@/components/notice";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import type { Route } from "@/lib/types";
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
          {can(me, "audit:read") ? <AuditTrail entityType="route" entityId={route.id} /> : null}
        </div>
      </div>
    </>
  );
}
