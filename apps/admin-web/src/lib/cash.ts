import type { Tone } from "@/components/ui/badge";
import type { BoardRow, Closeout, CloseoutLine } from "@/lib/cash-types";
import { formatNumber } from "@/lib/format";

/** Whole pounds with separators («2,940»); the board shows no piastres, like the design. */
export function egp(value: string | number): string {
  const n = Number(value);
  return formatNumber(Number.isInteger(n) ? n : Math.round(n * 100) / 100);
}

export const ROW_STATUS: Record<
  BoardRow["kind"] | Closeout["status"],
  { label: string; tone: Tone }
> = {
  WAITING: { label: "لم يُسجَّل التحصيل", tone: "warning" },
  PARTIAL: { label: "تحصيل جزئي", tone: "danger" },
  COLLECTED: { label: "تم التحصيل", tone: "success" },
  NOTHING_DUE: { label: "لا يوجد مستحق", tone: "neutral" },
  CLOSEOUT: { label: "تقفيل مُرسل", tone: "active" },
  DAY_OFF: { label: "إجازة", tone: "neutral" },
  OPEN_SHIFT: { label: "وردية مفتوحة", tone: "info" },
  ENDED_NOT_CLOSED: { label: "انتهت بدون تقفيل", tone: "warning" },
};

export function rowStatus(row: BoardRow): { label: string; tone: Tone } {
  return ROW_STATUS[row.closeout ? row.closeout.status : row.kind];
}

/** One line under the status, as in the design («المستحق 2,260 ج.م (منها 280 سابق)»). */
export function closeoutSummary(c: Closeout): string {
  const total = Number(c.total_due);
  const carried = Number(c.carried_before);
  switch (c.status) {
    case "WAITING":
      return `المستحق ${egp(total)} ج.م` + (carried > 0 ? ` (منها ${egp(carried)} سابق)` : "");
    case "PARTIAL":
      return `اتحصّل ${egp(c.collected)} · متبقي ${egp(c.remaining)} ج.م`;
    case "COLLECTED":
      return `اتحصّل ${egp(c.collected)} ج.م · لا يوجد متبقي`;
    case "NOTHING_DUE":
      return total < 0 ? `مستحق للسائق ${egp(-total)} ج.م` : "لا يوجد مبلغ للتسليم";
  }
}

/** Cell text for an expense line: «—» when none, the amount otherwise. */
export function lineValue(line: CloseoutLine | undefined): string {
  if (!line || Number(line.amount) === 0) return "—";
  return egp(line.amount);
}

/** A line the office rejected or voided is no longer deducted: the driver owes it. */
export function lineNotDeducted(line: CloseoutLine | undefined): boolean {
  return !!line && Number(line.amount) > 0 && !line.deducted;
}

/** Remaining after collecting `amount` of `totalDue` (never negative). */
export function remainingAfter(totalDue: string | number, amount: string): number {
  const paid = Number(amount.replace(/[^\d.]/g, ""));
  const due = Number(totalDue);
  if (!Number.isFinite(paid)) return Math.max(due, 0);
  return Math.max(Math.round((due - paid) * 100) / 100, 0);
}
