import { ROLE_LABELS_AR, ROLES, type Role } from "@go-daily/shared";
import { Plus } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
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
import { formatDateTime } from "@/lib/format";
import type { Page, User } from "@/lib/types";

export const metadata: Metadata = { title: "المستخدمون" };

export default async function UsersPage({ searchParams }: PageProps<"/users">) {
  const me = await requirePermission("users:read");
  const sp = await searchParams;
  const q = typeof sp.q === "string" ? sp.q : undefined;
  const role =
    typeof sp.role === "string" && (ROLES as readonly string[]).includes(sp.role)
      ? (sp.role as Role)
      : undefined;
  const status = sp.status === "active" || sp.status === "inactive" ? sp.status : undefined;
  const page = Math.max(1, Number(sp.page) || 1);

  const data = await api.get<Page<User>>("/users", {
    q,
    role,
    is_active: status === undefined ? undefined : status === "active",
    page,
    page_size: 20,
  });

  return (
    <>
      <PageHeader
        title="المستخدمون"
        description="حسابات الإدارة والتشغيل والمحاسبة والسائقين"
        actions={
          can(me, "users:manage") ? (
            <ButtonLink href="/users/new" variant="accent">
              <Plus className="size-4" aria-hidden="true" />
              مستخدم جديد
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
            <Input id="q" name="q" placeholder="بحث بالاسم أو رقم الهاتف" defaultValue={q} />
          </div>
          <div>
            <label htmlFor="role" className="sr-only">
              الصلاحية
            </label>
            <Select id="role" name="role" defaultValue={role ?? ""}>
              <option value="">كل الصلاحيات</option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS_AR[r]}
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
              <option value="active">مفعل</option>
              <option value="inactive">موقوف</option>
            </Select>
          </div>
          <Button type="submit" variant="secondary">
            تطبيق
          </Button>
        </form>
        {data.items.length === 0 ? (
          <EmptyState
            title="لا يوجد مستخدمون مطابقون"
            description="غيّر معايير البحث أو أضف مستخدمًا جديدًا."
          />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>الاسم</TH>
                <TH>رقم الهاتف</TH>
                <TH>الصلاحية</TH>
                <TH>الحالة</TH>
                <TH>آخر دخول</TH>
                <TH>
                  <span className="sr-only">إجراءات</span>
                </TH>
              </tr>
            </THead>
            <tbody>
              {data.items.map((u) => (
                <TR key={u.id}>
                  <TD className="font-medium">{u.full_name}</TD>
                  <TD className="ltr-nums">{u.phone}</TD>
                  <TD>{ROLE_LABELS_AR[u.role]}</TD>
                  <TD>
                    {u.is_active ? (
                      <Badge tone="success">مفعل</Badge>
                    ) : (
                      <Badge tone="neutral">موقوف</Badge>
                    )}
                  </TD>
                  <TD className="text-ink-muted">{formatDateTime(u.last_login_at)}</TD>
                  <TD className="text-end">
                    <Link
                      href={`/users/${u.id}`}
                      className="text-sm font-medium text-forest-700 hover:underline"
                    >
                      {can(me, "users:manage") ? "تعديل" : "عرض"}
                    </Link>
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
          basePath="/users"
          params={{ q, role, status }}
        />
      </Card>
    </>
  );
}
