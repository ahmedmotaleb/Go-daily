import { describe, expect, it } from "vitest";
import { cairoLocalToIso, isoToCairoLocal } from "./time";

describe("Cairo wall time conversion", () => {
  it("converts winter time (UTC+2)", () => {
    expect(cairoLocalToIso("2026-01-15T08:30")).toBe("2026-01-15T06:30:00.000Z");
  });

  it("converts summer time (UTC+3)", () => {
    expect(cairoLocalToIso("2026-07-15T08:30")).toBe("2026-07-15T05:30:00.000Z");
  });

  it("round-trips", () => {
    expect(isoToCairoLocal("2026-07-15T05:30:00.000Z")).toBe("2026-07-15T08:30");
    expect(isoToCairoLocal(cairoLocalToIso("2026-01-02T23:59"))).toBe("2026-01-02T23:59");
  });

  it("returns undefined/empty for blanks and garbage", () => {
    expect(cairoLocalToIso("")).toBeUndefined();
    expect(cairoLocalToIso("yesterday")).toBeUndefined();
    expect(isoToCairoLocal(null)).toBe("");
  });
});
