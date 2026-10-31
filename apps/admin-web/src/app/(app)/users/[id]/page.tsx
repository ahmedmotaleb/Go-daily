import { MANAGEABLE_ROLES, ROLE_LABELS_AR } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditTrail } from "@/components/audit-trail";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import type { User } from "@/lib/types";
import { resetPasswordAction, setUserActiveAction, updateUserAction } from "../actions";
import { UserForm } from "../user-form";
import { ActiveToggleForm, ResetPasswordForm } from "./user-admin-forms";

export const metadata: Metadata = { title: "بيانات المستخدم" };

export default async function UserDetailPage({ params, searchParams }: PageProps<"/users/[id]">) {
  const me = await requirePermission("users:read");
  const { id } = await params;
  const sp = await searchParams;
  const user = await api.get<User | null>(`/users/${id}`, undefined, { allow404: true });
  if (!user) notFound();

  const manageable = MANAGEABLE_ROLES[me.role] ?? [];
  const canManage = can(me, "users:manage") && manageable.includes(user.role);
  const isSelf = me.id === user.id;

  return (
    <>
      <PageHeader
        title={user.full_name}
        breadcrumb={<Link href="/users">المستخدمون</Link>}
        description={`${ROLE_LABELS_AR[user.role]} · آخر دخول: ${formatDateTime(user.last_login_at)}`}
        actions={user.is_active ? <Badge tone="success">مفعل</Badge> : <Badge>موقوف</Badge>}
      />
      {sp.created === "1" ? (
        <Alert tone="success" className="mb-4">
          تم إنشاء المستخدم بنجاح.
        </Alert>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="البيانات الأساسية" />
            <CardBody>
              {canManage ? (
                <UserForm
                  action={updateUserAction.bind(null, user.id)}
                  roles={isSelf ? [user.role] : manageable}
                  user={user}
                />
              ) : (
                <dl className="grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-ink-muted">رقم الهاتف</dt>
                    <dd className="ltr-nums font-medium">{user.phone}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-muted">البريد الإلكتروني</dt>
                    <dd className="font-medium">{user.email ?? "—"}</dd>
                  </div>
                </dl>
              )}
            </CardBody>
          </Card>
          {canManage && !isSelf ? (
            <Card>
              <CardHeader
                title="كلمة المرور"
                description="تعيين كلمة مرور جديدة للمستخدم عند نسيانها."
              />
              <CardBody>
                <ResetPasswordForm action={resetPasswordAction.bind(null, user.id)} />
              </CardBody>
            </Card>
          ) : null}
        </div>
        <div className="space-y-6">
          {canManage && !isSelf ? (
            <Card>
              <CardHeader title="حالة الحساب" />
              <CardBody>
                <ActiveToggleForm
                  action={setUserActiveAction.bind(null, user.id, !user.is_active)}
                  active={user.is_active}
                />
              </CardBody>
            </Card>
          ) : null}
          {can(me, "audit:read") ? <AuditTrail entityType="user" entityId={user.id} /> : null}
        </div>
      </div>
    </>
  );
}
