import clsx from "clsx";
import type { ReactNode } from "react";

/**
 * Status badge tones (design system): soft background, dark text that meets
 * 4.5:1, and an optional dot in the indicator shade.
 * success = green, warning = amber, danger = red, neutral = gray,
 * info = blue, active = dark forest (e.g. "in progress", "uploading").
 */
export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "active";

const tones: Record<Tone, string> = {
  neutral: "bg-neutral-100 text-neutral-700",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info",
  active: "bg-forest-100 text-forest-800",
};

export const DOT: Record<Tone, string> = {
  neutral: "bg-neutral-400",
  success: "bg-lime-600",
  warning: "bg-amber-400",
  danger: "bg-red-400",
  info: "bg-blue-400",
  active: "bg-forest-800",
};

export function Badge({
  tone = "neutral",
  dot = false,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {dot ? (
        <span aria-hidden="true" className={clsx("size-[7px] rounded-full", DOT[tone])} />
      ) : null}
      {children}
    </span>
  );
}
