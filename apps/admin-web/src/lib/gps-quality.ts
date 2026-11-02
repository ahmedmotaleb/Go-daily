import type { Tone } from "@/components/ui/badge";
import type { GpsQuality, QualityCheck, QualityGrade } from "@/lib/types";

export const GRADE_AR: Record<QualityGrade, string> = {
  EXCELLENT: "ممتاز",
  GOOD: "جيد",
  NEEDS_REVIEW: "يحتاج مراجعة",
  INSUFFICIENT: "بيانات غير كافية",
};

export const GRADE_TONE: Record<QualityGrade, Tone> = {
  EXCELLENT: "success",
  GOOD: "active",
  NEEDS_REVIEW: "warning",
  INSUFFICIENT: "neutral",
};

export const CHECK_AR: Record<QualityCheck["code"], string> = {
  COVERAGE: "تغطية مدة الوردية",
  LONGEST_GAP: "أطول انقطاع",
  MEDIAN_ACCURACY: "الدقة المعتادة (الوسيط)",
  LOW_ACCURACY_SHARE: "نقاط منخفضة الدقة",
  IMPOSSIBLE_JUMPS: "قفزات غير ممكنة",
  MOCK_POINTS: "نقاط من مصدر وهمي",
  STALE_SHARE: "نقاط وصلت متأخرة",
};

export const INSUFFICIENT_AR: Record<NonNullable<GpsQuality["insufficient_reason"]>, string> = {
  NOT_STARTED: "الوردية لم تبدأ بعد.",
  TOO_SHORT: "مدة الوردية أقصر من أن يُحكم على جودة بياناتها.",
  TOO_FEW_POINTS: "عدد النقاط الصالحة قليل جدًا للحكم على الجودة. لم يتم تقدير أي بيانات ناقصة.",
};

const UNIT_AR: Record<string, string> = {
  "%": "٪",
  min: "دقيقة",
  m: "متر",
  points: "نقطة",
};

/** "95 ٪", "10 دقيقة" — a value with its Arabic unit. */
export function withUnit(value: number, unit: string): string {
  const shown = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return `${shown} ${UNIT_AR[unit] ?? unit}`;
}

/** The rule a check passed or failed, e.g. "≥ 95 ٪" or "≤ 10 دقيقة". */
export function thresholdText(check: QualityCheck, which: "excellent" | "good"): string {
  const sign = check.higher_is_better ? "≥" : "≤";
  return `${sign} ${withUnit(check[which], check.unit)}`;
}

/** Seconds as a short Arabic duration for sync delays. */
export function delayText(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} ثانية`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} دقيقة`;
  return `${(seconds / 3600).toFixed(1)} ساعة`;
}
