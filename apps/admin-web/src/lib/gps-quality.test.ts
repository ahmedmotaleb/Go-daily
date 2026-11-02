import { describe, expect, it } from "vitest";
import { delayText, thresholdText, withUnit } from "@/lib/gps-quality";
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
    expect(thresholdText(coverage, "excellent")).toBe("≥ 95 ٪");
    expect(
      thresholdText({ ...coverage, unit: "min", higher_is_better: false, good: 30 }, "good"),
    ).toBe("≤ 30 دقيقة");
  });

  it("formats values and delays", () => {
    expect(withUnit(83.3, "%")).toBe("83.3 ٪");
    expect(withUnit(2, "points")).toBe("2 نقطة");
    expect(delayText(null)).toBe("—");
    expect(delayText(5)).toBe("5 ثانية");
    expect(delayText(900)).toBe("15 دقيقة");
    expect(delayText(7200)).toBe("2.0 ساعة");
  });
});
