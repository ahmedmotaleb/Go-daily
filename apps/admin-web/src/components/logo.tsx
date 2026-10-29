import clsx from "clsx";

/** Go Daily wordmark: a route pin in lime on forest green. */
export function Logo({ className, inverted = false }: { className?: string; inverted?: boolean }) {
  return (
    <span className={clsx("inline-flex items-center gap-2", className)} dir="ltr">
      <svg viewBox="0 0 32 32" aria-hidden="true" className="size-8 shrink-0">
        <rect width="32" height="32" rx="8" fill="#123b2b" />
        <path
          d="M16 6.5c-4 0-7 3-7 6.9 0 4.9 5.6 10.6 6.4 11.4a.9.9 0 0 0 1.2 0c.8-.8 6.4-6.5 6.4-11.4 0-3.9-3-6.9-7-6.9Z"
          fill="#a8df33"
        />
        <circle cx="16" cy="13.3" r="2.6" fill="#123b2b" />
      </svg>
      <span
        className={clsx(
          "text-lg font-bold tracking-tight",
          inverted ? "text-white" : "text-forest-800",
        )}
      >
        Go <span className={inverted ? "text-lime-400" : "text-forest-600"}>Daily</span>
      </span>
    </span>
  );
}
