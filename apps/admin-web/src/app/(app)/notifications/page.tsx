import clsx from "clsx";
import type { Metadata } from "next";
import Link from "next/link";
import { ActionForm } from "@/components/forms/action-form";
import { Notice } from "@/components/notice";
import { Badge, type Tone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import type { AppNotification, NotificationSeverity } from "@/lib/notification-types";
import { spEnum, spPage } from "@/lib/search";
import type { Page } from "@/lib/types";
import { generateNotificationsAction, markAllReadAction, openNotificationAction } from "./actions";

export const metadata: Metadata = { title: "التنبيهات" };

const SEVERITY: Record<NotificationSeverity, { label: string; tone: Tone }> = {
  CRITICAL: { label: "عاجل", tone: "danger" },
  WARNING: { label: "تنبيه", tone: "warning" },
  INFO: { label: "للعلم", tone: "info" },
};

const VIEWS = {
  unread: "غير المقروءة",
  all: "الحالية",
  history: "السجل الكامل",
} as const;

export default async function NotificationsPage({ searchParams }: PageProps<"/notifications">) {
  const me = await requirePermission("notifications:read");
  const sp = await searchParams;
  const view = spEnum(sp, "view", Object.keys(VIEWS) as (keyof typeof VIEWS)[]) ?? "unread";
  const page = spPage(sp);
  const list = await api.get<Page<AppNotification>>("/notifications", {
    unread_only: view === "unread",
    include_cleared: view === "history",
    page,
    page_size: 30,
  });

  return (
    <>
      <PageHeader
        title="التنبيهات"
        description="مستندات تنتهي، صيانة مستحقة، انقطاع التتبع، حالات للمراجعة وسجلات مالية معلقة. يختفي التنبيه تلقائيًا عند زوال سببه."
      />
      <Notice code={typeof sp.notice === "string" ? sp.notice : undefined} />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <nav
          className="flex gap-1 rounded-lg border border-line bg-surface p-1"
          aria-label="عرض التنبيهات"
        >
          {(Object.keys(VIEWS) as (keyof typeof VIEWS)[]).map((v) => (
            <Link
              key={v}
              href={`/notifications?view=${v}`}
              aria-current={v === view ? "page" : undefined}
              className={clsx(
                "rounded-md px-3 py-1.5 text-sm",
                v === view
                  ? "bg-forest-700 font-semibold text-white"
                  : "text-ink-muted hover:bg-forest-50",
              )}
            >
              {VIEWS[v]}
            </Link>
          ))}
        </nav>
        <div className="flex flex-wrap gap-2">
          {can(me, "settings:manage") ? (
            <ActionForm
              action={generateNotificationsAction}
              submitLabel="تحديث الآن"
              variant="secondary"
            />
          ) : null}
          <ActionForm
            action={markAllReadAction}
            submitLabel="تحديد الكل كمقروء"
            variant="secondary"
          />
        </div>
      </div>
      <Card>
        <CardHeader title={VIEWS[view]} />
        {list.items.length === 0 ? (
          <EmptyState
            title={view === "unread" ? "لا توجد تنبيهات غير مقروءة" : "لا توجد تنبيهات"}
          />
        ) : (
          <ul className="divide-y divide-line">
            {list.items.map((n) => (
              <li
                key={n.id}
                className={clsx(
                  "flex flex-wrap items-start justify-between gap-3 px-4 py-3",
                  !n.read_at && !n.cleared_at && "bg-lime-50/40",
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={SEVERITY[n.severity].tone}>{SEVERITY[n.severity].label}</Badge>
                    <p
                      className={clsx("text-sm", n.read_at ? "text-ink" : "font-semibold text-ink")}
                    >
                      {n.title}
                    </p>
                  </div>
                  {n.body ? <p className="mt-1 text-sm text-ink-muted">{n.body}</p> : null}
                  <p className="ltr-nums mt-1 text-xs text-ink-muted">
                    {formatDateTime(n.created_at)}
                    {n.cleared_at ? " · زال السبب" : ""}
                  </p>
                </div>
                <form action={openNotificationAction.bind(null, n.id)}>
                  <button
                    type="submit"
                    className="rounded-md border border-line px-3 py-1.5 text-sm text-forest-700 hover:bg-forest-50"
                  >
                    {n.link ? "فتح" : "تحديد كمقروء"}
                  </button>
                </form>
              </li>
            ))}
          </ul>
        )}
        <Pagination
          page={list.page}
          pageSize={list.page_size}
          total={list.total}
          basePath="/notifications"
          params={{ view }}
        />
      </Card>
    </>
  );
}
