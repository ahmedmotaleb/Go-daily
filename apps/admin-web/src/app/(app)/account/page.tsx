import { ROLE_LABELS_AR } from "@go-daily/shared";
import type { Metadata } from "next";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Alert } from "@/components/ui/alert";
import { api } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { ChangePasswordForm } from "./change-password-form";
import { TwoFactorCard } from "./two-factor-card";

export const metadata: Metadata = { title: "حسابي" };

export default async function AccountPage() {
  const user = await getCurrentUser();
  const status = await api.get<{
    enabled: boolean;
    required: boolean;
    recovery_codes_left: number;
  }>("/auth/2fa");
  return (
    <>
      <PageHeader title="حسابي" description={`${user.full_name} · ${ROLE_LABELS_AR[user.role]}`} />
      {user.twofa_setup_required ? (
        <Alert tone="warning" className="mb-4 max-w-xl">
          فعّل التحقق بخطوتين أولًا؛ باقي الصفحات متاحة بعد التفعيل.
        </Alert>
      ) : null}
      <div className="space-y-6">
        <TwoFactorCard status={status} />
        <Card className="max-w-xl">
          <CardHeader title="تغيير كلمة المرور" />
          <CardBody>
            <ChangePasswordForm />
          </CardBody>
        </Card>
      </div>
    </>
  );
}
