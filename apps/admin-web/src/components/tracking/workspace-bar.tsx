import { ChevronRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";

/** Dark top bar of a full-screen workspace: logo, back to the dashboard, title, tools. */
export function WorkspaceBar({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center gap-4 bg-sidebar px-6 py-3 text-white">
      <Logo inverted width={96} />
      <span aria-hidden="true" className="h-7 w-px bg-white/20" />
      <Link
        href="/"
        className="flex min-h-11 items-center gap-2 text-sm text-white no-underline hover:text-lime-300"
      >
        <ChevronRight className="size-5" strokeWidth={1.9} aria-hidden="true" />
        لوحة التشغيل
      </Link>
      <h1 className="flex-[1_1_200px] text-xl font-bold">{title}</h1>
      {children}
    </header>
  );
}

/** Segmented toggle on the dark bar (links, so the URL holds the state). */
export function BarToggle({
  label,
  options,
}: {
  label: string;
  options: { href: string; label: string; active: boolean }[];
}) {
  return (
    <nav aria-label={label} className="flex gap-1 rounded-[var(--radius-control)] bg-white/10 p-1">
      {options.map((o) => (
        <Link
          key={o.href}
          href={o.href}
          aria-current={o.active ? "page" : undefined}
          className={
            o.active
              ? "rounded-lg bg-lime-400 px-3.5 py-2 text-[13px] font-bold text-forest-900"
              : "rounded-lg px-3.5 py-2 text-[13px] font-semibold text-[#c9d6d0] hover:text-white"
          }
        >
          {o.label}
        </Link>
      ))}
    </nav>
  );
}
