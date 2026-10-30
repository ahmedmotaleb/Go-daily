import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { LABEL_AR, STATUS_AR, STATUS_TONE } from "@/lib/exception-labels";
import type { ExceptionSummary, OperationalException } from "@/lib/exception-types";
import { formatNumber } from "@/lib/format";
import type { Page } from "@/lib/types";

/** Dashboard card: how many cases still need someone's attention. */
export async function ExceptionsSummaryCard() {
  const s = await api.get<ExceptionSummary>("/exceptions/summary");
  return (
    <Card>
      <CardBody className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 size-5 shrink-0 text-forest-700" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">حالات للمراجعة</p>
          {s.active === 0 ? (
            <p className="mt-1 text-sm text-ink-muted">لا توجد حالات مفتوحة.</p>
          ) : (
            <p className="mt-1 text-sm text-ink-muted">
              <span className="ltr-nums font-bold text-ink">{formatNumber(s.active)}</span> حالة
              تحتاج متابعة
              {s.by_severity.HIGH ? (
                <>
                  ، منها{" "}
                  <span className="ltr-nums font-bold text-danger">
                    {formatNumber(s.by_severity.HIGH)}
                  </span>{" "}
                  عالية الأهمية
                </>
              ) : null}
              .
            </p>
          )}
          <Link
            href="/exceptions"
            className="mt-2 inline-block text-sm font-medium text-forest-700 hover:underline"
          >
            عرض الحالات
          </Link>
        </div>
      </CardBody>
    </Card>
  );
}

/** Cases linked to one shift (shown on the shift page). */
export async function ShiftExceptions({ shiftId }: { shiftId: string }) {
  const page = await api.get<Page<OperationalException>>("/exceptions", {
    shift_id: shiftId,
    page_size: 20,
  });
  if (page.items.length === 0) return null;
  return (
    <Card>
      <CardHeader title="حالات للمراجعة" description="إشارات آلية على هذه الوردية، ليست أحكامًا" />
      <CardBody>
        <ul className="divide-y divide-line">
          {page.items.map((e) => (
            <li
              key={e.id}
              className="flex flex-wrap items-start justify-between gap-2 py-2 text-sm"
            >
              <div className="min-w-0">
                <Link
                  href={`/exceptions/${e.id}`}
                  className="font-semibold text-forest-700 hover:underline"
                >
                  {e.rule_title}
                </Link>
                <p className="text-xs text-ink-muted">
                  {LABEL_AR[e.label]} · {e.summary}
                </p>
              </div>
              <Badge tone={STATUS_TONE[e.status]}>{STATUS_AR[e.status]}</Badge>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
