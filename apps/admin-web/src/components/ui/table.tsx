import clsx from "clsx";
import type { ComponentProps } from "react";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto">
      <table className={clsx("w-full min-w-[640px] text-start text-sm", className)} {...props} />
    </div>
  );
}

export function THead(props: ComponentProps<"thead">) {
  return <thead className="border-b border-line bg-neutral-50 text-xs text-ink-muted" {...props} />;
}

export function TH({ className, ...props }: ComponentProps<"th">) {
  return (
    <th scope="col" className={clsx("px-4 py-2.5 text-start font-medium", className)} {...props} />
  );
}

export function TR({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      className={clsx("border-b border-line last:border-0 hover:bg-neutral-50/60", className)}
      {...props}
    />
  );
}

export function TD({ className, ...props }: ComponentProps<"td">) {
  return <td className={clsx("px-4 py-3 align-middle", className)} {...props} />;
}
