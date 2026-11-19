"use client";

import { ROLE_LABELS_AR, type Role } from "@go-daily/shared";
import { useActionState } from "react";
import { Alert } from "@/components/ui/alert";
import { Checkbox, Field, Input, Select } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import { formKey, initialFormState, type FormState } from "@/lib/forms";
import type { User } from "@/lib/types";

type Props = {
  action: (state: FormState, formData: FormData) => Promise<FormState>;
  roles: readonly Role[];
  user?: User;
};

export function UserForm({ action, roles, user }: Props) {
  const [state, formAction] = useActionState(action, initialFormState);
  const v = (key: keyof User & string) =>
    state.values?.[key] ?? (user ? String(user[key] ?? "") : undefined);
  const err = state.fieldErrors ?? {};
  const isEdit = Boolean(user);
  return (
    <form
      key={formKey(state, user?.updated_at)}
      action={formAction}
      className="space-y-5"
      noValidate
    >
      {state.message ? <Alert tone={state.ok ? "success" : "danger"}>{state.message}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="الاسم بالكامل" htmlFor="full_name" error={err.full_name} required>
          <Input
            id="full_name"
            name="full_name"
            defaultValue={v("full_name")}
            invalid={!!err.full_name}
            required
          />
        </Field>
        <Field
          label="رقم الهاتف"
          htmlFor="phone"
          error={err.phone}
          hint="رقم موبايل مصري، مثل 01012345678"
          required
        >
          <Input
            id="phone"
            name="phone"
            type="tel"
            defaultValue={v("phone")}
            invalid={!!err.phone}
            required
          />
        </Field>
        <Field label="البريد الإلكتروني (اختياري)" htmlFor="email" error={err.email}>
          <Input
            id="email"
            name="email"
            type="email"
            defaultValue={v("email")}
            invalid={!!err.email}
          />
        </Field>
        <Field label="الصلاحية" htmlFor="role" error={err.role} required>
          <Select
            id="role"
            name="role"
            defaultValue={v("role") ?? ""}
            invalid={!!err.role}
            required
          >
            {isEdit ? null : <option value="">اختر الصلاحية</option>}
            {roles.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS_AR[r]}
              </option>
            ))}
          </Select>
        </Field>
        {!isEdit ? (
          <Field
            label="كلمة المرور المبدئية"
            htmlFor="password"
            error={err.password}
            hint="8 أحرف على الأقل. سلّمها للمستخدم بطريقة آمنة."
            required
          >
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              invalid={!!err.password}
              required
            />
          </Field>
        ) : null}
      </div>
      {!isEdit ? (
        <Checkbox
          name="is_active"
          label="الحساب مفعل"
          defaultChecked={state.values ? state.values.is_active === "on" : true}
        />
      ) : null}
      <div className="flex justify-end">
        <SubmitButton>{isEdit ? "حفظ التعديلات" : "إنشاء المستخدم"}</SubmitButton>
      </div>
    </form>
  );
}
