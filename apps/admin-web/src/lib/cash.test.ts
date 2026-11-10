import { describe, expect, it } from "vitest";
import { closeoutSummary, lineNotDeducted, lineValue, remainingAfter } from "@/lib/cash";
import type { Closeout, CloseoutLine } from "@/lib/cash-types";

const base = { total_due: "0", carried_before: "0", collected: "0", remaining: "0" };
const c = (over: Partial<Closeout>) => ({ ...base, ...over }) as Closeout;
const line = (amount: string, deducted = true) =>
  ({ key: "toll", label: "الكارتة", amount, deducted }) as CloseoutLine;

describe("cash board helpers", () => {
  it("summarises each status like the design", () => {
    expect(
      closeoutSummary(c({ status: "WAITING", total_due: "2260", carried_before: "280" })),
    ).toBe("المستحق 2,260 ج.م (منها 280 سابق)");
    expect(closeoutSummary(c({ status: "PARTIAL", collected: "1130", remaining: "270" }))).toBe(
      "اتحصّل 1,130 · متبقي 270 ج.م",
    );
    expect(closeoutSummary(c({ status: "COLLECTED", collected: "1980" }))).toBe(
      "اتحصّل 1,980 ج.م · لا يوجد متبقي",
    );
    expect(closeoutSummary(c({ status: "NOTHING_DUE", total_due: "-150" }))).toBe(
      "مستحق للسائق 150 ج.م",
    );
  });

  it("shows empty lines as a dash and flags lines no longer deducted", () => {
    expect(lineValue(undefined)).toBe("—");
    expect(lineValue(line("0"))).toBe("—");
    expect(lineValue(line("450"))).toBe("450");
    expect(lineNotDeducted(line("120", false))).toBe(true);
    expect(lineNotDeducted(line("120"))).toBe(false);
  });

  it("computes what stays due after a collection", () => {
    expect(remainingAfter("1980", "1700")).toBe(280);
    expect(remainingAfter("1980", "2,000")).toBe(0);
    expect(remainingAfter("1980", "")).toBe(1980);
  });
});
