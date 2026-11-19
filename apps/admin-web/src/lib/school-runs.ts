import type { SchoolRunVerification } from "@/lib/types";

/** "متأخر 18 دقيقة" / "قبل الموعد بـ 5 دقائق" / "في الموعد". */
export function delayText(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes > 0) return `متأخر ${minutes} دقيقة`;
  if (minutes < 0) return `قبل الموعد بـ ${-minutes} دقيقة`;
  return "في الموعد";
}

/** One line per fact a reviewer needs, in plain Arabic. */
export function verificationLines(v: SchoolRunVerification): string[] {
  const lines = [
    `المحطات: ${v.reached_stops.length} من ${v.required_stops.length}` +
      (v.missing_stops.length ? ` (لم تُدرك: ${v.missing_stops.join("، ")})` : ""),
    `البداية: ${delayText(v.start_delay_minutes)} · الوصول: ${delayText(v.arrival_delay_minutes)}`,
    `تغطية GPS: ${v.gps_coverage_pct}٪ (المطلوب ${v.min_gps_coverage_pct}٪)`,
  ];
  if (v.max_deviation_m !== null) {
    lines.push(
      `أقصى ابتعاد عن خط المحطات: ${v.max_deviation_m} م` +
        (v.max_deviation_m > v.corridor_m ? " — أكبر من النطاق المسموح" : ""),
    );
  }
  return lines;
}
