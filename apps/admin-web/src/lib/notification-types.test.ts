import { describe, expect, it } from "vitest";
import { safeInternalLink } from "./notification-types";

describe("safeInternalLink", () => {
  it("keeps internal paths", () => {
    expect(safeInternalLink("/vehicles/1f0e")).toBe("/vehicles/1f0e");
    expect(safeInternalLink("/finance/fuel?status=SUBMITTED")).toBe(
      "/finance/fuel?status=SUBMITTED",
    );
  });

  it("rejects anything that could leave the app", () => {
    expect(safeInternalLink("https://evil.example")).toBeNull();
    expect(safeInternalLink("//evil.example")).toBeNull();
    expect(safeInternalLink("/x\\y")).toBeNull();
    expect(safeInternalLink("javascript:alert(1)")).toBeNull();
    expect(safeInternalLink(null)).toBeNull();
  });
});
