import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";
import { RECONCILIATION_AR, RECONCILIATION_TONE, signedKm } from "@/lib/gps-quality";
import type { OdometerReconciliation } from "@/lib/types";

const MISSING_AR: Record<OdometerReconciliation["missing"][number], string> = {
  ODOMETER: "قراءة عداد البداية أو النهاية غير موجودة.",
  GPS: "تغطية GPS أقل من المطلوب للمقارنة؛ الفرق المعروض لا يُعتبر فرقًا حقيقيًا.",
};

/** GPS vs odometer for one shift; missing data is shown as missing, not as a difference. */
export function OdometerReconciliationPanel({ rec }: { rec: OdometerReconciliation }) {
  if (rec.status === "NOT_COMPLETED") return null;
  const originals = [
    rec.original_start_odometer_km !== null
      ? `البداية ${formatNumber(rec.original_start_odometer_km)} كم`
      : null,
    rec.original_end_odometer_km !== null
      ? `النهاية ${formatNumber(rec.original_end_odometer_km)} كم`
      : null,
  ].filter((x): x is string => x !== null);
  const facts: [string, string][] = [
    ["كم العداد", rec.odometer_km === null ? "—" : `${formatNumber(rec.odometer_km)} كم`],
    ["كم GPS", rec.gps_km === null ? "—" : `${formatNumber(rec.gps_km)} كم`],
    ["الفرق", signedKm(rec.difference_km)],
    ["الفرق (%)", rec.difference_pct === null ? "—" : `${formatNumber(rec.difference_pct)} ٪`],
    ["المسموح", rec.allowed_km === null ? "—" : `${formatNumber(rec.allowed_km)} كم`],
    ["تغطية GPS", rec.gps_coverage_pct === null ? "—" : `${formatNumber(rec.gps_coverage_pct)} ٪`],
  ];
  return (
    <section aria-labelledby="odometer-rec-title" className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="odometer-rec-title" className="text-sm font-semibold">
          مطابقة العداد مع GPS
        </h3>
        <Badge tone={RECONCILIATION_TONE[rec.status]}>{RECONCILIATION_AR[rec.status]}</Badge>
        {rec.odometer_corrected ? <Badge tone="info">قراءة مصححة</Badge> : null}
      </div>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {facts.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 border-b border-line py-1">
            <dt className="text-ink-muted">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {rec.missing.map((m) => (
        <p key={m} className="text-xs text-ink-muted">
          {MISSING_AR[m]}
        </p>
      ))}
      <p className="text-xs text-ink-muted">
        المسموح هو الأكبر بين {formatNumber(rec.tolerance_km)} كم و{formatNumber(rec.tolerance_pct)}
        ٪ من المسافة الأكبر، ولا تتم المقارنة إذا قلّت تغطية GPS عن{" "}
        {formatNumber(rec.min_gps_coverage_pct)}٪.
      </p>
      {originals.length > 0 ? (
        <p className="text-xs text-ink-muted">
          القراءات كما أُدخلت أولًا قبل التصحيح: {originals.join("، ")}. خطوات التصحيح في سجل
          الوردية.
        </p>
      ) : null}
    </section>
  );
}
