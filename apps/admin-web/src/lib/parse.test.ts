import { describe, expect, it } from "vitest";
import { compact, decimal, int } from "./parse";

function fd(entries: Record<string, string>) {
  const f = new FormData();
  for (const [k, v] of Object.entries(entries)) f.set(k, v);
  return f;
}

describe("form parsing", () => {
  it("parses integers including Arabic-Indic digits and separators", () => {
    expect(int(fd({ a: "182,000" }), "a")).toBe(182000);
    expect(int(fd({ a: "١٢٣" }), "a")).toBe(123);
    expect(int(fd({ a: "" }), "a")).toBeUndefined();
    expect(int(fd({ a: "12x" }), "a")).toBe("12x");
  });

  it("keeps decimals as strings", () => {
    expect(decimal(fd({ a: "١٢٣٫٥٠" }), "a")).toBe("123.50");
    expect(decimal(fd({ a: "1,250.75" }), "a")).toBe("1250.75");
  });

  it("drops undefined keys", () => {
    expect(compact({ a: 1, b: undefined, c: null })).toEqual({ a: 1, c: null });
  });
});
