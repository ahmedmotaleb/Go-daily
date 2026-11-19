import type { Metadata } from "next";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime, formatNumber } from "@/lib/format";

export const metadata: Metadata = { title: "جودة البيانات" };

type DataQuality = {
  missing: {
    code: string;
    title: string;
    why: string;
    count: number;
    examples: { title: string; link: string | null }[];
  }[];
  review: { rule_code: string; title: string; count: number }[];
  generated_at: string;
};

/** U49: what is missing or unfinished, kept apart from cases that need review. */
export default async function DataQualityPage() {
  const me = await requirePermission("reports:read");
  const data = await api.get<DataQuality>("/data-quality");
  const open = data.missing.filter((c) => c.count > 0);
  const clean = data.missing.filter((c) => c.count === 0);
  return (
    <>
      <PageHeader
        title="جودة البيانات"
        description={`ما ينقص السجلات أو لم يكتمل بعد · آخر فحص ${formatDateTime(data.generated_at)}`}
      />
      <Alert tone="info" className="mb-6">
        هذه الصفحة عن البيانات الناقصة فقط (لم تُسجل أو لم تُرسل أو لم تكتمل)، وليست عن أي شبهة.
        الحالات غير المعتادة لها قسم منفصل أدناه وفي مركز المراجعة.
      </Alert>

      <section aria-labelledby="missing" className="space-y-4">
        <h2 id="missing" className="text-lg font-bold">
          بيانات ناقصة
        </h2>
        {open.length === 0 ? (
          <p className="text-sm text-ink-muted">لا توجد بيانات ناقصة في الفحوص الحالية.</p>
        ) : null}
        <div className="grid gap-4 lg:grid-cols-2">
          {open.map((c) => (
            <Card key={c.code}>
              <CardHeader
                title={c.title}
                description={c.why}
                actions={<Badge tone="warning">{formatNumber(c.count)}</Badge>}
              />
              <CardBody>
                <ul className="space-y-1.5 text-sm">
                  {c.examples.map((e, i) => (
                    <li key={`${c.code}-${i}`}>
                      {e.link ? (
                        <Link href={e.link} className="text-primary hover:underline">
                          {e.title}
                        </Link>
                      ) : (
                        e.title
                      )}
                    </li>
                  ))}
                </ul>
                {c.count > c.examples.length ? (
                  <p className="mt-2 text-xs text-ink-muted">
                    وأكثر: {formatNumber(c.count - c.examples.length)}
                  </p>
                ) : null}
              </CardBody>
            </Card>
          ))}
        </div>
        {clean.length ? (
          <p className="text-sm text-ink-soft">مكتمل: {clean.map((c) => c.title).join("، ")}.</p>
        ) : null}
      </section>

      <section aria-labelledby="review" className="mt-10 space-y-4">
        <h2 id="review" className="text-lg font-bold">
          حالات تحتاج مراجعة
        </h2>
        <p className="text-sm text-ink-soft">
          أنماط غير معتادة اكتشفتها قواعد المراجعة؛ ليست بيانات ناقصة ولا دليلًا على مخالفة.
        </p>
        <Card>
          {data.review.length === 0 ? (
            <p className="px-5 py-4 text-sm text-ink-muted">لا توجد حالات مفتوحة.</p>
          ) : (
            <ul className="divide-y divide-line">
              {data.review.map((r) => (
                <li
                  key={r.rule_code}
                  className="flex items-center justify-between px-5 py-3 text-sm"
                >
                  {can(me, "exceptions:read") ? (
                    <Link
                      href={`/exceptions?rule_code=${r.rule_code}`}
                      className="font-medium hover:underline"
                    >
                      {r.title}
                    </Link>
                  ) : (
                    <span className="font-medium">{r.title}</span>
                  )}
                  <Badge tone="info">{formatNumber(r.count)}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </>
  );
}
