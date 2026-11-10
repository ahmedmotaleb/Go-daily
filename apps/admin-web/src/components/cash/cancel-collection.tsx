"use client";

import { useActionState, useId } from "react";
import { Input } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import { initialFormState, type FormState } from "@/lib/forms";

type Action = (state: FormState, formData: FormData) => Promise<FormState>;

/** Void a collection recorded by mistake (reason required, kept in history). */
export function CancelCollection({ action }: { action: Action }) {
  const [state, formAction] = useActionState(action, initialFormState);
  const id = useId();
  return (
    <details className="text-xs">
      <summary className="cursor-pointer font-semibold text-danger-action">إلغاء التحصيل</summary>
      <form action={formAction} className="mt-2 flex flex-col gap-2" noValidate>
        <label htmlFor={id} className="sr-only">
          سبب الإلغاء
        </label>
        <Input
          id={id}
          name="reason"
          placeholder="سبب الإلغاء"
          invalid={!!state.fieldErrors?.reason}
          className="h-9 text-xs"
        />
        {state.message && !state.ok ? (
          <p role="alert" className="text-danger">
            {state.message}
          </p>
        ) : null}
        <SubmitButton
          variant="danger"
          className="h-9 text-xs"
          pendingLabel="جارٍ الإلغاء…"
          confirm="إلغاء هذا التحصيل؟ سيعود المبلغ مستحقًا على السائق."
        >
          تأكيد الإلغاء
        </SubmitButton>
      </form>
    </details>
  );
}
