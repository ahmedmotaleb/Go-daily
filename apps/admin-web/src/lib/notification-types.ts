export type NotificationSeverity = "INFO" | "WARNING" | "CRITICAL";

export type AppNotification = {
  id: string;
  kind: string;
  severity: NotificationSeverity;
  title: string;
  body: string | null;
  link: string | null;
  created_at: string;
  read_at: string | null;
  cleared_at: string | null;
};

export type UnreadCount = { unread: number; critical: number };

/** Server-generated links are internal paths; anything else is ignored. */
export function safeInternalLink(link: string | null | undefined): string | null {
  if (!link || !/^\/[A-Za-z0-9\-/?=&_.]*$/.test(link) || link.startsWith("//")) return null;
  return link;
}
