import clsx from "clsx";
import type { ComponentProps } from "react";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    // `relative`: absolutely positioned cells content (e.g. sr-only labels)
    // stays inside the scroll box instead of widening the page.
    <div className="relative overflow-x-auto">
      <table className={clsx("w-full min-w-[640px] text-start text-sm", className)} {...props} />
    </div>
  );
}

export function THead(props: ComponentProps<"thead">) {
  return (
    <thead
      className="border-b border-line bg-neutral-50 text-xs font-semibold text-ink-muted"
      {...props}
    />
  );
}

export function TH({ className, ...props }: ComponentProps<"th">) {
  return (
    <th scope="col" className={clsx("px-4 py-3 text-start font-semibold", className)} {...props} />
  );
}

export function TR({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      className={clsx("border-b border-neutral-100 last:border-0 hover:bg-neutral-50", className)}
      {...props}
    />
  );
}

export function TD({ className, ...props }: ComponentProps<"td">) {
  return <td className={clsx("px-4 py-3 align-middle", className)} {...props} />;
}
