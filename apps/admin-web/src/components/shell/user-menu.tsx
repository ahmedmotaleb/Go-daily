import { ROLE_LABELS_AR } from "@go-daily/shared";
import { KeyRound, LogOut } from "lucide-react";
import Link from "next/link";
import { logoutAction } from "@/app/(app)/actions";
import type { CurrentUser } from "@/lib/types";

export function UserMenu({ user }: { user: CurrentUser }) {
  return (
    <div className="flex items-center gap-3">
      <div className="hidden text-end sm:block">
        <p className="text-sm font-semibold text-ink">{user.full_name}</p>
        <p className="text-xs text-ink-muted">{ROLE_LABELS_AR[user.role]}</p>
      </div>
      <Link
        href="/account"
        className="rounded-[var(--radius-control)] p-2 text-ink-muted hover:bg-neutral-100 hover:text-ink"
        title="حسابي وكلمة المرور"
      >
        <KeyRound className="size-4" aria-hidden="true" />
        <span className="sr-only">حسابي</span>
      </Link>
      <form action={logoutAction}>
        <button
          type="submit"
          className="inline-flex items-center gap-1.5 rounded-[var(--radius-control)] px-3 py-2 text-sm text-ink-muted hover:bg-neutral-100 hover:text-ink"
        >
          <LogOut className="size-4" aria-hidden="true" />
          خروج
        </button>
      </form>
    </div>
  );
}
