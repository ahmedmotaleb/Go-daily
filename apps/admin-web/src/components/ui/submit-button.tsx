"use client";

import { useFormStatus } from "react-dom";
import { Button, type ButtonVariant } from "./button";

export function SubmitButton({
  children,
  pendingLabel = "جارٍ الحفظ…",
  variant = "primary",
  className,
  confirm,
}: {
  children: React.ReactNode;
  pendingLabel?: string;
  variant?: ButtonVariant;
  className?: string;
  /** Ask for confirmation first (financial or destructive actions). */
  confirm?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant={variant}
      disabled={pending}
      aria-busy={pending}
      className={className}
      onClick={(e) => {
        if (confirm && !window.confirm(confirm)) e.preventDefault();
      }}
    >
      {pending ? pendingLabel : children}
    </Button>
  );
}
