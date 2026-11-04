import clsx from "clsx";
import type { ReactNode } from "react";
import type { Tone } from "./badge";

const tones: Record<Exclude<Tone, "active" | "neutral">, string> = {
  success: "border-lime-200 bg-success-soft text-success",
  warning: "border-[#f3d9a8] bg-warning-soft text-warning",
  danger: "border-[#f6d3d2] bg-danger-soft text-danger",
  info: "border-[#c9daee] bg-info-soft text-info",
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: keyof typeof tones;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={clsx(
        "rounded-[var(--radius-control)] border px-4 py-3 text-sm",
        tones[tone],
        className,
      )}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      {children ? <div className={title ? "mt-1" : undefined}>{children}</div> : null}
    </div>
  );
}
