import { ROLE_LABELS_AR } from "@go-daily/shared";
import { AppNav } from "@/components/shell/app-nav";
import { NotificationBell } from "@/components/shell/notification-bell";
import { UserMenu } from "@/components/shell/user-menu";
import { api } from "@/lib/api";
import { can, getCurrentUser } from "@/lib/auth";
import type { ExceptionSummary } from "@/lib/exception-types";
import { formatLongDate } from "@/lib/format";
import { navForPermissions } from "@/lib/navigation";

/** Open review cases for the sidebar badge; the shell never fails a page over it. */
async function openCases(): Promise<number> {
  try {
    return (await api.get<ExceptionSummary>("/exceptions/summary")).active;
  } catch {
    return 0;
  }
}

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const user = await getCurrentUser();
  const items = navForPermissions(user.permissions);
  const badges: Record<string, number> = can(user, "exceptions:read")
    ? { "/exceptions": await openCases() }
    : {};
  return (
    <div className="min-h-screen bg-background lg:flex">
      <AppNav
        items={items}
        badges={badges}
        userName={user.full_name}
        roleLabel={ROLE_LABELS_AR[user.role]}
      />
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 sm:px-8">
          <p className="text-[13px] text-ink-muted">{formatLongDate(new Date())}</p>
          <div className="flex items-center gap-2">
            {can(user, "notifications:read") ? <NotificationBell /> : null}
            <UserMenu user={user} />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-8">{children}</main>
      </div>
    </div>
  );
}
