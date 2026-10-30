import { AppNav } from "@/components/shell/app-nav";
import { NotificationBell } from "@/components/shell/notification-bell";
import { UserMenu } from "@/components/shell/user-menu";
import { can, getCurrentUser } from "@/lib/auth";
import { navForPermissions } from "@/lib/navigation";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const user = await getCurrentUser();
  const items = navForPermissions(user.permissions);
  return (
    <div className="min-h-screen lg:flex">
      <AppNav items={items} />
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-end gap-3 border-b border-line bg-surface px-4 py-2.5 sm:px-6">
          {can(user, "notifications:read") ? <NotificationBell /> : null}
          <UserMenu user={user} />
        </header>
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
