import { formatMoney } from "@/lib/format";
import type { ExpectedRevenueModel, RouteRevenueRate } from "@/lib/types";

export const RATE_MODEL_AR: Record<ExpectedRevenueModel, string> = {
  PER_LOOP: "سعر لكل دورة (ذهاب وعودة)",
  PER_LEG: "سعر لكل اتجاه",
  PASSENGERS_X_FARE: "عدد الركاب المتوقع × الأجرة",
};

/** "120.00 ج.م لكل دورة" etc.: what one rate expects, in words. */
export function rateText(rate: RouteRevenueRate): string {
  switch (rate.model) {
    case "PER_LOOP":
      return `${formatMoney(rate.amount_per_loop)} لكل دورة`;
    case "PER_LEG":
      return `${formatMoney(rate.amount_per_leg)} لكل اتجاه`;
    case "PASSENGERS_X_FARE":
      return `${rate.passengers_per_leg ?? "—"} راكب × ${formatMoney(rate.fare)} لكل اتجاه`;
  }
}
