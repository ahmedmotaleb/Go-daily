"use client";

import { useRouter } from "next/navigation";

/** Day selector on light cards; changing it reloads the page for that day. */
export function DayPicker({ value, basePath }: { value: string; basePath: string }) {
  const router = useRouter();
  return (
    <label className="flex items-center gap-2 text-[13px] text-ink-soft">
      اليوم
      <input
        type="date"
        value={value}
        onChange={(e) => {
          if (/^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) {
            router.push(`${basePath}?day=${e.target.value}`, { scroll: false });
          }
        }}
        className="ltr-nums h-10 rounded-[var(--radius-control)] border border-line-strong bg-surface px-3 text-sm text-ink"
      />
    </label>
  );
}
