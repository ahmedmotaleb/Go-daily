import { describe, expect, it } from "vitest";
import { delayText, verificationLines } from "@/lib/school-runs";

describe("school run evidence", () => {
  it("words delays", () => {
    expect(delayText(18)).toBe("متأخر 18 دقيقة");
    expect(delayText(-5)).toBe("قبل الموعد بـ 5 دقيقة");
    expect(delayText(0)).toBe("في الموعد");
    expect(delayText(null)).toBe("—");
  });

  it("lists stops, delays, coverage and deviation", () => {
    const lines = verificationLines({
      required_stops: [
        { id: "a", name: "الموقف" },
        { id: "b", name: "محطة الحي" },
        { id: "c", name: "المدرسة" },
      ],
      reached_stops: ["a", "c"],
      missing_stops: ["محطة الحي"],
      arrived_at: null,
      start_delay_minutes: 2,
      arrival_delay_minutes: -3,
      late_grace_minutes: 10,
      gps_points: 120,
      gps_coverage_pct: 92.5,
      min_gps_coverage_pct: 60,
      max_deviation_m: 2400,
      corridor_m: 2000,
    });
    expect(lines[0]).toBe("المحطات: 2 من 3 (لم تُدرك: محطة الحي)");
    expect(lines[2]).toContain("92.5");
    expect(lines[3]).toContain("أكبر من النطاق المسموح");
  });
});
