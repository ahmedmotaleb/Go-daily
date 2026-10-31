import { describe, expect, it } from "vitest";
import { daysUntil, formatDate, formatDateTime, formatMoney, formatNumber } from "./format";

describe("formatMoney", () => {
  it("formats EGP with two decimals and Latin digits", () => {
    const out = formatMoney("1234.5");
    expect(out).toContain("1,234.50");
    expect(out).toMatch(/ج\.م\.|EGP/);
  });

  it("returns a dash for missing values", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney("")).toBe("—");
    expect(formatMoney("abc")).toBe("—");
  });
});

describe("formatNumber", () => {
  it("formats numbers with grouping", () => {
    expect(formatNumber(125000)).toBe("125,000");
  });
});

describe("formatDate", () => {
  it("does not shift plain calendar dates", () => {
    expect(formatDate("2026-01-05")).toBe("05/01/2026");
  });

  it("shows instants in Cairo time", () => {
    // 22:30 UTC on Jan 5 is already Jan 6 in Cairo (UTC+2).
    expect(formatDate("2026-01-05T22:30:00Z")).toContain("06");
  });
});

describe("formatDateTime", () => {
  it("renders a Cairo-local time", () => {
    expect(formatDateTime("2026-01-05T10:00:00Z")).toContain("12:00");
  });
});

describe("daysUntil", () => {
  it("counts calendar days in Cairo", () => {
    const now = new Date("2026-03-01T10:00:00Z");
    expect(daysUntil("2026-03-11", now)).toBe(10);
    expect(daysUntil("2026-02-27", now)).toBe(-2);
  });
});
