import clsx from "clsx";
import type { LucideIcon } from "lucide-react";

/** KPI tile: label + icon, a large Inter figure with its unit, and one line of context. */
export function KpiCard({
  label,
  value,
  unit,
  sub,
  icon: Icon,
  tone = "default",
  href,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  icon: LucideIcon;
  tone?: "default" | "hero" | "alert";
  href?: string;
}) {
  const hero = tone === "hero";
  const alert = tone === "alert";
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span
          className={clsx("text-[13px] font-medium", hero ? "text-[#c9d6d0]" : "text-ink-soft")}
        >
          {label}
        </span>
        <span
          aria-hidden="true"
          className={clsx(
            "flex size-[34px] items-center justify-center rounded-[10px]",
            hero
              ? "bg-lime-400/15 text-lime-400"
              : alert
                ? "bg-danger-soft text-danger"
                : "bg-forest-50 text-forest-800",
          )}
        >
          <Icon className="size-[18px]" strokeWidth={1.8} />
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span
          className={clsx(
            "ltr-nums text-[28px] leading-tight font-bold tracking-[-0.01em]",
            hero ? "text-white" : alert ? "text-danger" : "text-ink",
          )}
        >
          {value}
        </span>
        {unit ? (
          <span className={clsx("text-[13px]", hero ? "text-[#c9d6d0]" : "text-ink-muted")}>
            {unit}
          </span>
        ) : null}
      </div>
      {sub ? (
        <span
          className={clsx(
            "text-xs",
            hero ? "text-lime-400" : alert ? "text-danger" : "text-ink-muted",
          )}
        >
          {sub}
        </span>
      ) : null}
    </>
  );
  const classes = clsx(
    "flex flex-col gap-2.5 rounded-[18px] border p-[18px]",
    hero
      ? "border-forest-800 bg-forest-800 shadow-[0_10px_24px_rgb(16_61_50/0.18)]"
      : "border-line bg-surface shadow-[var(--shadow-card)]",
    href && "transition-colors hover:border-forest-300",
  );
  return href ? (
    <a href={href} className={classes}>
      {body}
    </a>
  ) : (
    <div className={classes}>{body}</div>
  );
}
