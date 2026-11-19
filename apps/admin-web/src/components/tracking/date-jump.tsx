"use client";

import { useRouter } from "next/navigation";

/** Date picker on the dark bar; changing it reloads the page for that day. */
export function DateJump({
  value,
  basePath,
  extra = {},
}: {
  value: string;
  basePath: string;
  extra?: Record<string, string>;
}) {
  const router = useRouter();
  return (
    <label className="flex h-11 items-center gap-2 rounded-[var(--radius-control)] bg-white/10 px-3 text-[13px]">
      <span className="text-[#c9d6d0]">التاريخ</span>
      <input
        type="date"
        value={value}
        onChange={(e) => {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) return;
          const sp = new URLSearchParams({ ...extra, date: e.target.value });
          router.push(`${basePath}?${sp.toString()}`);
        }}
        className="ltr-nums border-0 bg-transparent text-sm text-white [color-scheme:dark] focus-visible:shadow-none"
      />
    </label>
  );
}
