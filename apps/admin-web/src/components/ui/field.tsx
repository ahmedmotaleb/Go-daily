import clsx from "clsx";
import type { ComponentProps, ReactNode } from "react";

const control =
  "block w-full rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm text-ink placeholder:text-neutral-400 focus:border-forest-500 focus:outline-none focus:ring-2 focus:ring-lime-300 disabled:bg-neutral-50 aria-[invalid=true]:border-danger";

export function Field({
  label,
  htmlFor,
  error,
  hint,
  required,
  children,
  className,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
        {label}
        {required ? (
          <span className="ms-1 text-danger" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${htmlFor}-hint`} className="text-xs text-ink-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function Input({
  className,
  invalid,
  ...props
}: ComponentProps<"input"> & { invalid?: boolean }) {
  return (
    <input
      aria-invalid={invalid || undefined}
      aria-describedby={invalid && props.id ? `${props.id}-error` : undefined}
      className={clsx(control, "h-10", className)}
      {...props}
    />
  );
}

export function Select({
  className,
  invalid,
  ...props
}: ComponentProps<"select"> & { invalid?: boolean }) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={clsx(control, "h-10 pe-8", className)}
      {...props}
    />
  );
}

export function Textarea({
  className,
  invalid,
  ...props
}: ComponentProps<"textarea"> & { invalid?: boolean }) {
  return (
    <textarea
      aria-invalid={invalid || undefined}
      className={clsx(control, "min-h-24 py-2", className)}
      {...props}
    />
  );
}

export function Checkbox({
  label,
  className,
  ...props
}: ComponentProps<"input"> & { label: string }) {
  return (
    <label className={clsx("inline-flex items-center gap-2 text-sm text-ink", className)}>
      <input type="checkbox" className="size-4 rounded border-line accent-forest-700" {...props} />
      {label}
    </label>
  );
}
