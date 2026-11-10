import type { Metadata } from "next";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { formatDateTime, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "أحداث الأمان" };

type Security = {
  hours: number;
  counts: Record<string, number>;
  hourly_failures: { hour: string; count: number }[];
  spike: boolean;
  top_accounts: { label: string; count: number }[];
  top_addresses: { label: string; count: number }[];
  unknown_number_attempts: number;
  recent: { at: string; action: string; label: string; user: string | null; ip: string | null }[];
  warnings: { code: string; message: string }[];
};

const COUNTS: [string, string][] = [
  ["failed_logins", "محاولات دخول فاشلة"],
  ["lockouts", "إيقاف مؤقت للحساب"],
  ["twofa_failures", "رموز تحقق خاطئة"],
  ["reauth_failures", "فشل تأكيد الهوية"],
  ["twofa_resets", "إعادة ضبط/إيقاف التحقق بخطوتين"],
  ["permission_denied", "محاولات بدون صلاحية"],
  ["password_resets", "كلمات مرور عيّنتها الإدارة"],
];

const HOUR = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  hour12: false,
});

/** U36: security events from the audit log (no secrets or national IDs). */
export default async function SecurityPage({ searchParams }: PageProps<"/security">) {
  await requirePermission("settings:manage");
  const { hours } = await searchParams;
  const h = [24, 72, 168].includes(Number(hours)) ? Number(hours) : 24;
  const data = await api.get<Security>("/security/events", { hours: h });
  const max = Math.max(1, ...data.hourly_failures.map((x) => x.count));

  return (
    <>
      <PageHeader
        title="أحداث الأمان"
        description={`آخر ${formatNumber(h)} ساعة من سجل التدقيق`}
        actions={
          <div className="flex gap-2 text-sm">
            {[24, 72, 168].map((n) => (
              <a
                key={n}
                href={`/security?hours=${n}`}
                className={n === h ? "font-bold text-primary" : "text-ink-soft hover:underline"}
              >
                {n === 168 ? "أسبوع" : `${n} ساعة`}
              </a>
            ))}
          </div>
        }
      />
      {data.spike ? (
        <Alert tone="danger" className="mb-4">
          ارتفاع غير معتاد في محاولات الدخول الفاشلة خلال ساعة واحدة — راجع العناوين والحسابات
          أدناه.
        </Alert>
      ) : null}
      {data.warnings.length ? (
        <Card className="mb-6">
          <CardHeader title="تنبيهات الإعداد" />
          <CardBody>
            <ul className="space-y-1.5 text-sm">
              {data.warnings.map((w) => (
                <li key={w.code}>• {w.message}</li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {COUNTS.map(([key, label]) => (
          <Card key={key}>
            <CardBody>
              <div className="text-xs text-ink-muted">{label}</div>
              <div className="ltr-nums text-2xl font-bold">
                {formatNumber(data.counts[key] ?? 0)}
              </div>
            </CardBody>
          </Card>
        ))}
        <Card>
          <CardBody>
            <div className="text-xs text-ink-muted">محاولات لأرقام غير مسجلة</div>
            <div className="ltr-nums text-2xl font-bold">
              {formatNumber(data.unknown_number_attempts)}
            </div>
          </CardBody>
        </Card>
      </div>

      <Card className="mb-6">
        <CardHeader title="محاولات الدخول الفاشلة لكل ساعة" />
        <CardBody>
          <div
            className="flex h-32 items-end gap-0.5"
            dir="ltr"
            aria-label="رسم المحاولات لكل ساعة"
          >
            {data.hourly_failures.map((x) => (
              <div
                key={x.hour}
                title={`${HOUR.format(new Date(x.hour))}: ${x.count}`}
                className={x.count ? "flex-1 rounded-t bg-danger/70" : "flex-1 rounded-t bg-line"}
                style={{ height: `${Math.max(4, (x.count / max) * 100)}%` }}
              />
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        {[
          ["الحسابات الأكثر محاولات فاشلة", data.top_accounts],
          ["العناوين الأكثر محاولات فاشلة", data.top_addresses],
        ].map(([title, rows]) => (
          <Card key={title as string}>
            <CardHeader title={title as string} />
            {(rows as Security["top_accounts"]).length === 0 ? (
              <p className="px-5 py-4 text-sm text-ink-muted">لا شيء.</p>
            ) : (
              <ul className="divide-y divide-line">
                {(rows as Security["top_accounts"]).map((r) => (
                  <li key={r.label} className="flex justify-between px-5 py-2.5 text-sm">
                    <span className="ltr-nums">{r.label}</span>
                    <Badge tone="warning">{formatNumber(r.count)}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader title="آخر الأحداث" />
        {data.recent.length === 0 ? (
          <p className="px-5 py-4 text-sm text-ink-muted">لا توجد أحداث في هذه الفترة.</p>
        ) : (
          <ul className="divide-y divide-line">
            {data.recent.map((e, i) => (
              <li
                key={`${e.at}-${i}`}
                className="flex flex-wrap gap-x-4 gap-y-1 px-5 py-2.5 text-sm"
              >
                <span className="ltr-nums text-ink-soft">{formatDateTime(e.at)}</span>
                <span className="font-medium">{e.label}</span>
                {e.user ? <span>{e.user}</span> : null}
                {e.ip ? <span className="ltr-nums text-ink-muted">{e.ip}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
