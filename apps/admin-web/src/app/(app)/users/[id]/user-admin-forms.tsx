"use client";

import { useActionState } from "react";
import { Alert } from "@/components/ui/alert";
import { Field, Input } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import { initialFormState, type FormState } from "@/lib/forms";

type Action = (state: FormState, formData: FormData) => Promise<FormState>;

export function ResetPasswordForm({ action }: { action: Action }) {
  const [state, formAction] = useActionState(action, initialFormState);
  const err = state.fieldErrors ?? {};
  return (
    <form action={formAction} className="space-y-4" noValidate>
      {state.message ? <Alert tone={state.ok ? "success" : "danger"}>{state.message}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="كلمة المرور الجديدة" htmlFor="new_password" error={err.new_password} required>
          <Input
            id="new_password"
            name="new_password"
            type="password"
            autoComplete="new-password"
            required
          />
        </Field>
        <Field
          label="تأكيد كلمة المرور"
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
      </div>
      <div className="flex justify-end">
        <SubmitButton variant="secondary" confirm="سيتم إنهاء كل جلسات هذا المستخدم. متابعة؟">
          تعيين كلمة مرور جديدة
        </SubmitButton>
      </div>
    </form>
  );
}

export function ActiveToggleForm({ action, active }: { action: Action; active: boolean }) {
  const [state, formAction] = useActionState(action, initialFormState);
  return (
    <form action={formAction} className="space-y-3">
      {state.message ? <Alert tone={state.ok ? "success" : "danger"}>{state.message}</Alert> : null}
      <p className="text-sm text-ink-muted">
        {active
          ? "إيقاف الحساب يمنع الدخول فورًا وينهي كل الجلسات المفتوحة. لا يتم حذف أي بيانات."
          : "تفعيل الحساب يسمح للمستخدم بتسجيل الدخول مرة أخرى."}
      </p>
      <SubmitButton
        variant={active ? "danger" : "primary"}
        confirm={active ? "إيقاف هذا الحساب؟" : undefined}
        pendingLabel="جارٍ التنفيذ…"
      >
        {active ? "إيقاف الحساب" : "تفعيل الحساب"}
      </SubmitButton>
    </form>
  );
}
