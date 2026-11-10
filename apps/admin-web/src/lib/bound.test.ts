import { describe, expect, it } from "vitest";
import { boundId, boundOneOf, boundReturnPath } from "./bound";

describe("bound server-action arguments", () => {
  it("accepts only UUIDs as ids", () => {
    expect(boundId("0b6c7f1e-2a51-4c9a-9d5b-1f0e1c2d3e4f")).toBeTruthy();
    expect(() => boundId("../auth/logout")).toThrow();
    expect(() => boundId(42)).toThrow();
  });

  it("accepts only listed values", () => {
    expect(boundOneOf("approve", ["approve", "reject"] as const)).toBe("approve");
    expect(() => boundOneOf("../users", ["approve", "reject"] as const)).toThrow();
  });

  it("accepts only internal detail paths", () => {
    expect(boundReturnPath("/finance/fuel/0b6c7f1e-2a51-4c9a-9d5b-1f0e1c2d3e4f")).toBeTruthy();
    for (const bad of ["https://evil.example", "//evil.example", "/finance/../users", "/users/1"]) {
      expect(() => boundReturnPath(bad)).toThrow();
    }
  });
});
