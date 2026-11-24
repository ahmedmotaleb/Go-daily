import type { ReactNode } from "react";

/** Empty state: a soft icon tile, a short title and what to do next. */
export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2.5 px-6 py-12 text-center">
      {icon ? (
        <span
          aria-hidden="true"
          className="flex size-[52px] items-center justify-center rounded-2xl bg-forest-50 text-forest-800"
        >
          {icon}
        </span>
      ) : null}
      <p className="text-[15px] font-bold text-ink">{title}</p>
      {description ? <p className="max-w-md text-[13px] text-ink-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
