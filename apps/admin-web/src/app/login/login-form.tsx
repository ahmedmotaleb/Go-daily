"use client";

import { useActionState } from "react";
import { Alert } from "@/components/ui/alert";
import { Field, Input } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import { initialFormState } from "@/lib/forms";
import { loginAction } from "./actions";

export function LoginForm({ next }: { next?: string }) {
  const [state, action] = useActionState(loginAction, initialFormState);
  const challenge = state.values?.challenge;
  if (challenge) {
    return (
      <form action={action} className="space-y-4" noValidate>
        {state.message ? <Alert tone="danger">{state.message}</Alert> : null}
        <input type="hidden" name="next" value={next ?? "/"} />
        <input type="hidden" name="challenge" value={challenge} />
        <input type="hidden" name="phone" value={state.values?.phone ?? ""} />
        <p className="text-sm text-ink-soft">
          أدخل الرمز المكوّن من 6 أرقام من تطبيق المصادقة على هاتفك، أو أحد رموز الاسترداد.
        </p>
        <Field label="رمز التحقق" htmlFor="code" required>
          <Input
            id="code"
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            className="ltr-nums"
            required
            autoFocus
          />
        </Field>
        <SubmitButton className="w-full" pendingLabel="جارٍ التحقق…">
          تأكيد
        </SubmitButton>
      </form>
    );
  }
  return (
    <form action={action} className="space-y-4" noValidate>
      {state.message ? <Alert tone="danger">{state.message}</Alert> : null}
      <input type="hidden" name="next" value={next ?? "/"} />
      <Field label="رقم الهاتف" htmlFor="phone" required>
        <Input
          id="phone"
          name="phone"
          type="tel"
          inputMode="tel"
          autoComplete="username"
          placeholder="01012345678"
          defaultValue={state.values?.phone}
          required
          autoFocus
        />
      </Field>
      <Field label="كلمة المرور" htmlFor="password" required>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </Field>
      <SubmitButton className="w-full" pendingLabel="جارٍ تسجيل الدخول…">
        تسجيل الدخول
      </SubmitButton>
    </form>
  );
}
