import type { Tone } from "@/components/ui/badge";
import type { PlausibilityCheck } from "@/lib/finance-types";

export const CHECK_AR: Record<PlausibilityCheck["code"], string> = {
  ASSIGNMENT: "إسناد السائق للمركبة",
  SHIFT_TIME: "وقت الشراء والورديات",
  ODOMETER: "قراءة العداد",
  LOCATION: "موقع الشراء وموقع المركبة",
  QUANTITY: "الكمية",
  RAPID_REPEAT: "تكرار التموين",
  DUPLICATE: "سجل مكرر محتمل",
};

export const RESULT_AR: Record<PlausibilityCheck["result"], { label: string; tone: Tone }> = {
  PASS: { label: "سليم", tone: "success" },
  FAIL: { label: "مراجعة مطلوبة", tone: "warning" },
  NOT_CHECKABLE: { label: "لا يمكن الفحص", tone: "neutral" },
};

const MISSING_AR: Record<string, string> = {
  no_driver: "لا يوجد سائق في السجل",
  no_reading: "لم تُسجل قراءة العداد",
  no_purchase_location: "لم يُسجل موقع الشراء",
  no_vehicle_gps: "لا يوجد GPS للمركبة وقت الشراء",
};

/** Why a check passed, failed or could not run, in one line. */
export function checkExplanation(c: PlausibilityCheck): string {
  if (c.result === "NOT_CHECKABLE")
    return MISSING_AR[c.note ?? ""] ?? "البيانات اللازمة غير متوفرة";
  if (c.result === "FAIL") return c.note ?? "";
  return "";
}

/** Failures another review rule already raises: shown here, reviewed there. */
export function coveredNote(c: PlausibilityCheck): string | null {
  return c.covered_by ? `تظهر أيضًا كحالة مراجعة مستقلة (${c.covered_by})` : null;
}
