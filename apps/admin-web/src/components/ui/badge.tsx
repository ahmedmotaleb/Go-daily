import clsx from "clsx";
import type { ReactNode } from "react";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "active";

const tones: Record<Tone, string> = {
  neutral: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  success: "bg-success-soft text-success ring-forest-200",
  warning: "bg-warning-soft text-warning ring-amber-200",
  danger: "bg-danger-soft text-danger ring-red-200",
  info: "bg-info-soft text-info ring-teal-200",
  active: "bg-lime-100 text-forest-800 ring-lime-300",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
