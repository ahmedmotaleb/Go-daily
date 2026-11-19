import { MANAGEABLE_ROLES } from "@go-daily/shared";
import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { requirePermission } from "@/lib/auth";
import { createUserAction } from "../actions";
import { UserForm } from "../user-form";

export const metadata: Metadata = { title: "مستخدم جديد" };

export default async function NewUserPage() {
  const me = await requirePermission("users:manage");
  const roles = MANAGEABLE_ROLES[me.role] ?? [];
  return (
    <>
      <PageHeader title="مستخدم جديد" breadcrumb={<Link href="/users">المستخدمون</Link>} />
      <Card className="max-w-3xl">
        <CardBody>
          <UserForm action={createUserAction} roles={roles} />
        </CardBody>
      </Card>
    </>
  );
}
