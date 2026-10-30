import { COMPENSATION_METHOD_LABELS_AR } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditTrail } from "@/components/audit-trail";
import { Notice } from "@/components/notice";
import { AssignmentHistory, AssignmentPanel } from "@/components/domain/assignments";
import { EmploymentBadge, ExpiryBadge } from "@/components/domain/badges";
import { ActionForm } from "@/components/forms/action-form";
import { TextField } from "@/components/forms/fields";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDate, formatMoney } from "@/lib/format";
import type { Assignment, CompensationPlan, Driver, Page, Vehicle } from "@/lib/types";
import {
  addCompensationPlanAction,
  createDriverAccountAction,
  resetDriverPasswordAction,
  revealNationalIdAction,
  setDriverAccountActiveAction,
  updateDriverAction,
} from "../actions";
import { DriverForm } from "../driver-form";
import { CompensationPlanForm } from "./compensation-form";

export const metadata: Metadata = { title: "بيانات السائق" };

function planTerms(p: CompensationPlan): string {
  switch (p.method) {
    case "FIXED_MONTHLY":
      return `${formatMoney(p.fixed_monthly_amount)} شهريًا`;
    case "DAILY_WAGE":
      return `${formatMoney(p.daily_wage_amount)} يوميًا`;
    case "REVENUE_PERCENTAGE":
      return `${p.revenue_percentage}% من الإيراد المؤهل`;
    case "FIXED_PLUS_INCENTIVE":
      return `${formatMoney(p.fixed_monthly_amount)} شهريًا + ${p.incentive_percentage}% فوق ${formatMoney(p.incentive_threshold_amount)}`;
  }
}

export default async function DriverDetailPage({
  params,
  searchParams,
}: PageProps<"/drivers/[id]">) {
  const me = await requirePermission("drivers:read");
  const { id } = await params;
  const sp = await searchParams;
  const driver = await api.get<Driver | null>(`/drivers/${id}`, undefined, { allow404: true });
  if (!driver) notFound();

  const canEdit = can(me, "drivers:write");
  const canAssign = can(me, "assignments:write");
  const [history, vehicles, plans] = await Promise.all([
    can(me, "assignments:read")
      ? api.get<Page<Assignment>>(`/drivers/${id}/assignments`, { page_size: 50 })
      : Promise.resolve(null),
    canAssign && can(me, "vehicles:read")
      ? api.get<Page<Vehicle>>("/vehicles", { is_active: true, page_size: 100 })
      : Promise.resolve(null),
    can(me, "settlements:read")
      ? api.get<CompensationPlan[]>(`/drivers/${id}/compensation-plans`)
      : Promise.resolve(null),
  ]);
  const vehicleChoices = (vehicles?.items ?? []).map((v) => {
    const primary = v.current_assignments.find((a) => a.role === "PRIMARY");
    return {
      value: v.id,
      label: `${v.internal_code} · ${v.plate_number}${primary ? ` (مكلف: ${primary.driver_name})` : ""}`,
    };
  });

  return (
    <>
      <PageHeader
        title={driver.full_name}
        breadcrumb={<Link href="/drivers">السائقون</Link>}
        description={`هاتف: ${driver.phone}`}
        actions={<EmploymentBadge status={driver.employment_status} />}
      />
      {sp.created === "1" ? (
        <Alert tone="success" className="mb-4">
          تمت إضافة السائق.
        </Alert>
      ) : null}
      <Notice code={sp.notice} />
      {driver.license_status === "EXPIRED" ? (
        <Alert tone="danger" className="mb-4" title="رخصة القيادة منتهية">
          انتهت رخصة القيادة بتاريخ {formatDate(driver.license_expiry)}. راجع الرخصة قبل تكليف
          السائق بأي وردية.
        </Alert>
      ) : driver.license_status === "EXPIRING_SOON" ? (
        <Alert tone="warning" className="mb-4">
          رخصة القيادة تنتهي بتاريخ {formatDate(driver.license_expiry)}.
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="بيانات السائق"
              actions={<ExpiryBadge status={driver.license_status} date={driver.license_expiry} />}
            />
            <CardBody>
              {canEdit ? (
                <DriverForm action={updateDriverAction.bind(null, driver.id)} driver={driver} />
              ) : (
                <dl className="grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-ink-muted">رقم الرخصة</dt>
                    <dd className="ltr-nums font-medium">{driver.license_number ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-muted">الرقم القومي</dt>
                    <dd className="ltr-nums font-medium">{driver.national_id_masked ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-muted">تاريخ التعيين</dt>
                    <dd className="font-medium">{formatDate(driver.hire_date)}</dd>
                  </div>
                </dl>
              )}
            </CardBody>
          </Card>

          {history ? (
            <AssignmentHistory side="driver" items={history.items} total={history.total} />
          ) : null}

          {plans ? (
            <Card>
              <CardHeader
                title="طريقة احتساب المستحقات"
                description="الخطط محفوظة بتواريخها؛ تغيير الخطة لا يعدل الفترات السابقة"
              />
              {plans.length === 0 ? (
                <p className="px-5 py-4 text-sm text-ink-muted">لم يتم تحديد طريقة احتساب بعد.</p>
              ) : (
                <Table>
                  <THead>
                    <tr>
                      <TH>الطريقة</TH>
                      <TH>الشروط</TH>
                      <TH>من</TH>
                      <TH>إلى</TH>
                    </tr>
                  </THead>
                  <tbody>
                    {plans.map((p) => (
                      <TR key={p.id}>
                        <TD className="font-medium">{COMPENSATION_METHOD_LABELS_AR[p.method]}</TD>
                        <TD>{planTerms(p)}</TD>
                        <TD>{formatDate(p.effective_from)}</TD>
                        <TD>
                          {p.effective_to ? (
                            formatDate(p.effective_to)
                          ) : (
                            <Badge tone="active">سارية</Badge>
                          )}
                        </TD>
                      </TR>
                    ))}
                  </tbody>
                </Table>
              )}
              {can(me, "settlements:write") ? (
                <CardBody className="border-t border-line">
                  <details>
                    <summary className="cursor-pointer text-sm font-semibold text-forest-700">
                      إضافة خطة جديدة
                    </summary>
                    <div className="mt-3">
                      <CompensationPlanForm
                        action={addCompensationPlanAction.bind(null, driver.id)}
                      />
                    </div>
                  </details>
                </CardBody>
              ) : null}
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          {can(me, "assignments:read") ? (
            <AssignmentPanel
              side="driver"
              fixedId={driver.id}
              current={driver.current_assignments}
              choices={vehicleChoices}
              canWrite={canAssign}
              canAssign={driver.employment_status === "ACTIVE"}
              inactiveReason="لا يمكن تكليف سائق غير نشط."
            />
          ) : null}

          <Card>
            <CardHeader title="حساب تطبيق السائق" />
            <CardBody className="space-y-4">
              {driver.user_id === null ? (
                canEdit ? (
                  driver.employment_status === "ACTIVE" ? (
                    <ActionForm
                      action={createDriverAccountAction.bind(null, driver.id)}
                      submitLabel="إنشاء الحساب"
                      variant="accent"
                    >
                      <p className="text-sm text-ink-muted">
                        يسجل السائق الدخول في التطبيق برقم هاتفه {driver.phone}.
                      </p>
                      <TextField
                        name="password"
                        label="كلمة المرور"
                        type="password"
                        autoComplete="new-password"
                        required
                      />
                      <TextField
                        name="confirm_password"
                        label="تأكيد كلمة المرور"
                        type="password"
                        autoComplete="new-password"
                        required
                      />
                    </ActionForm>
                  ) : (
                    <p className="text-sm text-ink-muted">لا يمكن إنشاء حساب لسائق غير نشط.</p>
                  )
                ) : (
                  <p className="text-sm text-ink-muted">لا يوجد حساب تطبيق.</p>
                )
              ) : (
                <>
                  <p className="text-sm">
                    الحالة:{" "}
                    {driver.app_account_active ? (
                      <Badge tone="success">مفعل</Badge>
                    ) : (
                      <Badge>موقوف</Badge>
                    )}
                  </p>
                  {canEdit ? (
                    <>
                      <ActionForm
                        action={setDriverAccountActiveAction.bind(
                          null,
                          driver.id,
                          !driver.app_account_active,
                        )}
                        submitLabel={driver.app_account_active ? "إيقاف الحساب" : "تفعيل الحساب"}
                        variant={driver.app_account_active ? "danger" : "primary"}
                        confirm={
                          driver.app_account_active
                            ? "إيقاف حساب التطبيق وإنهاء جلساته؟"
                            : undefined
                        }
                        version={driver.updated_at + String(driver.app_account_active)}
                      />
                      <details>
                        <summary className="cursor-pointer text-sm font-medium text-ink-muted hover:text-ink">
                          تعيين كلمة مرور جديدة
                        </summary>
                        <div className="mt-3">
                          <ActionForm
                            action={resetDriverPasswordAction.bind(null, driver.id)}
                            submitLabel="تعيين"
                            variant="secondary"
                          >
                            <TextField
                              name="new_password"
                              label="كلمة المرور الجديدة"
                              type="password"
                              autoComplete="new-password"
                              required
                            />
                            <TextField
                              name="confirm_password"
                              label="تأكيد كلمة المرور"
                              type="password"
                              autoComplete="new-password"
                              required
                            />
                          </ActionForm>
                        </div>
                      </details>
                    </>
                  ) : null}
                </>
              )}
            </CardBody>
          </Card>

          {can(me, "drivers:read_sensitive") && driver.national_id_masked ? (
            <Card>
              <CardHeader
                title="الرقم القومي"
                description="يتم تسجيل كل عملية عرض في سجل المراجعة"
              />
              <CardBody>
                <ActionForm
                  action={revealNationalIdAction.bind(null, driver.id)}
                  submitLabel="عرض الرقم القومي"
                  variant="secondary"
                >
                  <p className="ltr-nums text-sm text-ink-muted">{driver.national_id_masked}</p>
                </ActionForm>
              </CardBody>
            </Card>
          ) : null}

          {can(me, "audit:read") ? <AuditTrail entityType="driver" entityId={driver.id} /> : null}
        </div>
      </div>
    </>
  );
}
