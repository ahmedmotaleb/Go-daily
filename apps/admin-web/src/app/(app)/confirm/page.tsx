import type { Metadata } from "next";
import { ActionForm } from "@/components/forms/action-form";
import { TextField } from "@/components/forms/fields";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { getCurrentUser } from "@/lib/auth";
import { confirmAction } from "./actions";

export const metadata: Metadata = { title: "تأكيد الهوية" };

/** U35: sensitive actions need a recent password (and 2FA) confirmation. */
export default async function ConfirmPage({ searchParams }: PageProps<"/confirm">) {
  const user = await getCurrentUser();
  const { next } = await searchParams;
  return (
    <>
      <PageHeader
        title="تأكيد الهوية"
        description="هذا إجراء حساس. أكّد كلمة المرور للمتابعة، ثم أعد تنفيذ الإجراء."
      />
      <Card className="max-w-md">
        <CardHeader title={user.full_name} />
        <CardBody>
          <ActionForm action={confirmAction} submitLabel="تأكيد والعودة">
            <input type="hidden" name="next" value={typeof next === "string" ? next : "/"} />
            <TextField
              name="password"
              label="كلمة المرور"
              type="password"
              autoComplete="current-password"
              required
            />
            {user.twofa_enabled ? (
              <TextField
                name="code"
                label="رمز التحقق"
                inputMode="numeric"
                autoComplete="one-time-code"
                className="ltr-nums"
                required
              />
            ) : null}
          </ActionForm>
        </CardBody>
      </Card>
    </>
  );
}
