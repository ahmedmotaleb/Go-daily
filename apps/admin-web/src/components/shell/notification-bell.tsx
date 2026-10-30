import { Bell } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { UnreadCount } from "@/lib/notification-types";

/** Header bell with the unread count; critical ones turn the badge red. */
export async function NotificationBell() {
  let counts: UnreadCount = { unread: 0, critical: 0 };
  try {
    counts = await api.get<UnreadCount>("/notifications/unread-count");
  } catch {
    // The header must never break a page; the inbox shows errors itself.
  }
  const label = counts.unread
    ? `التنبيهات: ${formatNumber(counts.unread)} غير مقروءة`
    : "التنبيهات";
  return (
    <Link
      href="/notifications"
      aria-label={label}
      title={label}
      className="relative inline-flex size-9 items-center justify-center rounded-full text-ink-muted hover:bg-forest-50 hover:text-forest-800"
    >
      <Bell className="size-5" aria-hidden="true" />
      {counts.unread ? (
        <span
          className={`ltr-nums absolute -top-0.5 -left-0.5 min-w-5 rounded-full px-1 text-center text-[11px] leading-5 font-bold text-white ${
            counts.critical ? "bg-danger" : "bg-forest-700"
          }`}
        >
          {counts.unread > 99 ? "99+" : formatNumber(counts.unread)}
        </span>
      ) : null}
    </Link>
  );
}
