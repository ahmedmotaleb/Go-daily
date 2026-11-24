import { describe, expect, it } from "vitest";
import { durationText, legSummary } from "@/lib/route-legs";

const base = {
  started_at: "2026-03-01T06:30:00Z",
  seconds: 270,
  from_stop_id: "a",
  to_stop_id: "b",
  visited_stop_ids: [],
  in_route_order: true,
};

describe("leg evidence", () => {
  it("formats durations", () => {
    expect(durationText(45)).toBe("45 ث");
    expect(durationText(270)).toBe("4 د 30 ث");
    expect(durationText(180)).toBe("3 د");
  });

  it("explains completed, incomplete and rejected legs", () => {
    expect(legSummary(base)).toBe("المدة 4 د 30 ث");
    expect(legSummary({ ...base, reason: "returned_to_start" })).toContain("نقطة البداية");
    const rejected = legSummary({
      ...base,
      seconds: 60,
      reason: "faster_than_minimum",
      min_seconds: 180,
    });
    expect(rejected).toContain("الحد الأدنى 3 د");
    expect(legSummary({ ...base, visited_stop_ids: ["m"], in_route_order: false })).toContain(
      "بغير ترتيب المسار",
    );
  });
});
