import { Badge } from "@/components/ui/badge";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import {
  CHECK_AR,
  delayText,
  GRADE_AR,
  GRADE_TONE,
  INSUFFICIENT_AR,
  thresholdText,
  withUnit,
} from "@/lib/gps-quality";
import type { GpsQuality } from "@/lib/types";

/**
 * Shift GPS quality with every number behind it: the grade is the worst
 * result among the checks, and each check shows its value and thresholds.
 */
export function GpsQualityPanel({ quality }: { quality: GpsQuality }) {
  const m = quality.metrics;
  const facts: [string, string][] = [
    ["مدة الوردية", `${formatNumber(m.duration_minutes)} دقيقة`],
    ["النقاط (الصالحة)", `${formatNumber(m.points)} (${formatNumber(m.valid_points)})`],
    ["التغطية", m.coverage_pct === null ? "—" : withUnit(m.coverage_pct, "%")],
    ["عدد الانقطاعات", formatNumber(m.gaps)],
    ["الدقة المعتادة", m.median_accuracy_m === null ? "—" : withUnit(m.median_accuracy_m, "m")],
    ["تأخير الإرسال المعتاد", delayText(m.median_sync_delay_s)],
    ["تأخير الإرسال (95٪ من النقاط)", delayText(m.p95_sync_delay_s)],
    ["نقاط وصلت متأخرة", formatNumber(m.stale_points)],
  ];
  return (
    <section aria-labelledby="gps-quality-title" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="gps-quality-title" className="text-sm font-semibold">
          جودة بيانات GPS
        </h3>
        <Badge tone={GRADE_TONE[quality.grade]}>{GRADE_AR[quality.grade]}</Badge>
        {quality.partial ? (
          <span className="text-xs text-ink-muted">الوردية جارية: الأرقام حتى الآن</span>
        ) : null}
      </div>
      {quality.insufficient_reason ? (
        <p className="text-sm text-ink-muted">{INSUFFICIENT_AR[quality.insufficient_reason]}</p>
      ) : (
        <p className="text-xs text-ink-muted">
          التقييم هو أضعف نتيجة بين البنود التالية. القيم محسوبة من النقاط المسجلة فقط.
        </p>
      )}
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-4">
        {facts.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 border-b border-line py-1">
            <dt className="text-ink-muted">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {quality.checks.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>البند</TH>
              <TH>القيمة</TH>
              <TH>ممتاز</TH>
              <TH>جيد</TH>
              <TH>النتيجة</TH>
            </TR>
          </THead>
          <tbody>
            {quality.checks.map((c) => (
              <TR key={c.code}>
                <TD>{CHECK_AR[c.code]}</TD>
                <TD>{withUnit(c.value, c.unit)}</TD>
                <TD className="text-ink-muted">{thresholdText(c, "excellent")}</TD>
                <TD className="text-ink-muted">{thresholdText(c, "good")}</TD>
                <TD>
                  <Badge tone={GRADE_TONE[c.grade]}>{GRADE_AR[c.grade]}</Badge>
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      ) : null}
    </section>
  );
}
