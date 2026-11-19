import { describe, expect, it } from "vitest";
import type { PlausibilityCheck } from "@/lib/finance-types";
import { checkExplanation, coveredNote } from "@/lib/fuel-plausibility";

const base: PlausibilityCheck = {
  code: "ODOMETER",
  result: "PASS",
  observed: 1000,
  threshold: null,
  note: null,
  covered_by: null,
  details: {},
};

describe("fuel plausibility labels", () => {
  it("explains missing data instead of guessing", () => {
    expect(checkExplanation({ ...base, result: "NOT_CHECKABLE", note: "no_reading" })).toBe(
      "لم تُسجل قراءة العداد",
    );
    expect(checkExplanation({ ...base, result: "NOT_CHECKABLE", note: "other" })).toBe(
      "البيانات اللازمة غير متوفرة",
    );
  });

  it("shows the failure note and the rule that covers it", () => {
    const fail = { ...base, result: "FAIL" as const, note: "قراءة أقل", covered_by: "FUEL_FAR" };
    expect(checkExplanation(fail)).toBe("قراءة أقل");
    expect(coveredNote(fail)).toContain("FUEL_FAR");
    expect(coveredNote(base)).toBeNull();
  });
});
