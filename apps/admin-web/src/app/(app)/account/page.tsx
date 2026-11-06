import { ROLE_LABELS_AR } from "@go-daily/shared";
import type { Metadata } from "next";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { getCurrentUser } from "@/lib/auth";
import { ChangePasswordForm } from "./change-password-form";

export const metadata: Metadata = { title: "حسابي" };

export default async function AccountPage() {
  const user = await getCurrentUser();
  return (
    <>
      <PageHeader title="حسابي" description={`${user.full_name} · ${ROLE_LABELS_AR[user.role]}`} />
      <Card className="max-w-xl">
        <CardHeader title="تغيير كلمة المرور" />
        <CardBody>
          <ChangePasswordForm />
        </CardBody>
      </Card>
    </>
  );
}
