"use client";

import { useActionState } from "react";
import { Alert } from "@/components/ui/alert";
import { Field, Input } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import { initialFormState } from "@/lib/forms";
import { changePasswordAction } from "./actions";

export function ChangePasswordForm() {
  const [state, formAction] = useActionState(changePasswordAction, initialFormState);
  const err = state.fieldErrors ?? {};
  return (
    <form action={formAction} className="space-y-4" noValidate>
      {state.message ? <Alert tone={state.ok ? "success" : "danger"}>{state.message}</Alert> : null}
      <Field
        label="كلمة المرور الحالية"
        htmlFor="current_password"
        error={err.current_password}
        required
      >
        <Input
          id="current_password"
          name="current_password"
          type="password"
          autoComplete="current-password"
          required
        />
      </Field>
      <Field
        label="كلمة المرور الجديدة"
        htmlFor="new_password"
        error={err.new_password}
        hint="8 أحرف على الأقل"
        required
      >
        <Input
          id="new_password"
          name="new_password"
          type="password"
          autoComplete="new-password"
          required
        />
      </Field>
      <Field
        label="تأكيد كلمة المرور الجديدة"
        htmlFor="confirm_password"
        error={err.confirm_password}
        required
      >
        <Input
          id="confirm_password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          required
        />
      </Field>
      <div className="flex justify-end">
        <SubmitButton>تغيير كلمة المرور</SubmitButton>
      </div>
    </form>
  );
}
