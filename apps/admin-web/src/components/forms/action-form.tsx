"use client";

import clsx from "clsx";
import { createContext, useActionState, useContext, type ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import type { ButtonVariant } from "@/components/ui/button";
import { SubmitButton } from "@/components/ui/submit-button";
import { formKey, initialFormState, type FormState } from "@/lib/forms";

type Action = (state: FormState, formData: FormData) => Promise<FormState>;

const FormStateContext = createContext<FormState>(initialFormState);

/** Field errors and echoed values of the enclosing ActionForm. */
export function useActionFormState(): FormState {
  return useContext(FormStateContext);
}

/**
 * Generic server-action form. Fields placed inside (see fields.tsx) show
 * server validation errors and keep submitted values after a failure.
 */
export function ActionForm({
  action,
  submitLabel,
  pendingLabel,
  variant = "primary",
  confirm,
  children,
  className,
  version,
  footer,
}: {
  action: Action;
  submitLabel: string;
  pendingLabel?: string;
  variant?: ButtonVariant;
  confirm?: string;
  children?: ReactNode;
  className?: string;
  /** Changes when the underlying record changes (e.g. updated_at) to refresh defaults. */
  version?: string;
  footer?: ReactNode;
}) {
  const [state, formAction] = useActionState(action, initialFormState);
  return (
    <form
      key={formKey(state, version)}
      action={formAction}
      className={clsx("space-y-4", className)}
      noValidate
    >
      {state.message ? <Alert tone={state.ok ? "success" : "danger"}>{state.message}</Alert> : null}
      <FormStateContext value={state}>{children}</FormStateContext>
      <div className="flex flex-wrap items-center justify-end gap-3">
        {footer}
        <SubmitButton variant={variant} confirm={confirm} pendingLabel={pendingLabel}>
          {submitLabel}
        </SubmitButton>
      </div>
    </form>
  );
}
