import type { LegDetails } from "@/lib/types";

const REASON_AR: Record<NonNullable<LegDetails["reason"]>, string> = {
  returned_to_start: "عادت المركبة لنقطة البداية دون الوصول للطرف الآخر",
  session_ended: "انتهى التشغيل قبل الوصول للطرف الآخر",
  faster_than_minimum: "أسرع من أقل زمن مسموح للاتجاه، فلم يُحتسب (غالبًا تذبذب في GPS)",
};

/** "4 د 30 ث" — whole minutes and seconds. */
export function durationText(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s} ث`;
  return s === 0 ? `${m} د` : `${m} د ${s} ث`;
}

/** One line of leg evidence for reviewers. */
export function legSummary(d: LegDetails): string {
  const parts: string[] = [];
  if (d.reason) parts.push(REASON_AR[d.reason]);
  if (d.seconds !== null) parts.push(`المدة ${durationText(d.seconds)}`);
  if (d.reason === "faster_than_minimum" && d.min_seconds !== undefined) {
    parts.push(`الحد الأدنى ${durationText(d.min_seconds)}`);
  }
  if (d.visited_stop_ids.length > 0) {
    parts.push(
      `محطات وسيطة: ${d.visited_stop_ids.length}${d.in_route_order ? "" : " (بغير ترتيب المسار)"}`,
    );
  }
  return parts.join(" · ");
}
