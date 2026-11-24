import { describe, expect, it } from "vitest";
import { delayText, signedKm, thresholdText, withUnit } from "@/lib/gps-quality";
import type { QualityCheck } from "@/lib/types";

const coverage: QualityCheck = {
  code: "COVERAGE",
  value: 83.3,
  unit: "%",
  excellent: 95,
  good: 80,
  higher_is_better: true,
  grade: "GOOD",
};

describe("gps quality labels", () => {
  it("shows the threshold direction", () => {
    expect(thresholdText(coverage, "excellent")).toBe("95 ٪ أو أكثر");
    expect(
      thresholdText({ ...coverage, unit: "min", higher_is_better: false, good: 30 }, "good"),
    ).toBe("30 دقيقة أو أقل");
  });

  it("never shows a zero limit as a comparison", () => {
    const mock = {
      ...coverage,
      code: "MOCK_POINTS" as const,
      unit: "points",
      excellent: 0,
      good: 0,
    };
    expect(thresholdText({ ...mock, higher_is_better: false }, "good")).toBe("لا شيء");
  });

  it("formats values and delays", () => {
    expect(withUnit(83.3, "%")).toBe("83.3 ٪");
    expect(withUnit(2, "points")).toBe("2 نقطة");
    expect(delayText(null)).toBe("—");
    expect(delayText(5)).toBe("5 ثانية");
    expect(delayText(900)).toBe("15 دقيقة");
    expect(delayText(7200)).toBe("2.0 ساعة");
  });

  it("signs distance differences", () => {
    expect(signedKm(null)).toBe("—");
    expect(signedKm(3.24)).toBe("العداد أكثر بـ 3.2 كم");
    expect(signedKm(-1)).toBe("العداد أقل بـ 1.0 كم");
    expect(signedKm(0)).toBe("لا فرق");
  });
});
