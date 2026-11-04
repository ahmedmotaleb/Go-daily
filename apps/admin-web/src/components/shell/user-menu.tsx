import { ROLE_LABELS_AR } from "@go-daily/shared";
import { KeyRound, LogOut } from "lucide-react";
import Link from "next/link";
import { logoutAction } from "@/app/(app)/actions";
import type { CurrentUser } from "@/lib/types";

export function UserMenu({ user }: { user: CurrentUser }) {
  return (
    <div className="flex items-center gap-2">
      <span className="sr-only">
        {user.full_name} — {ROLE_LABELS_AR[user.role]}
      </span>
      <Link
        href="/account"
        className="flex size-11 items-center justify-center rounded-[var(--radius-control)] border border-line bg-surface text-ink hover:bg-neutral-50"
        title="حسابي وكلمة المرور"
      >
        <KeyRound className="size-5" strokeWidth={1.7} aria-hidden="true" />
        <span className="sr-only">حسابي</span>
      </Link>
      <form action={logoutAction}>
        <button
          type="submit"
          className="inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-control)] border border-line bg-surface px-3 text-sm font-semibold text-ink hover:bg-neutral-50"
        >
          <LogOut className="size-5" strokeWidth={1.7} aria-hidden="true" />
          خروج
        </button>
      </form>
    </div>
  );
}
