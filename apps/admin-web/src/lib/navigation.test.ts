import { describe, expect, it } from "vitest";
import { isActivePath, navForPermissions } from "./navigation";

describe("navigation", () => {
  it("hides items without permission", () => {
    const labels = navForPermissions(["vehicles:read"]).map((i) => i.href);
    expect(labels).toContain("/");
    expect(labels).toContain("/vehicles");
    expect(labels).not.toContain("/users");
  });

  it("shows /pilot only with every permission GET /api/v1/pilot requires", () => {
    const hrefs = (perms: string[]) => navForPermissions(perms).map((i) => i.href);
    // Operations: cash and tracking, no revenue. Accountant: cash and revenue, no tracking.
    expect(hrefs(["cash:read", "tracking:read"])).not.toContain("/pilot");
    expect(hrefs(["cash:read", "revenue:read"])).not.toContain("/pilot");
    expect(hrefs(["cash:read", "revenue:read", "tracking:read"])).toContain("/pilot");
  });

  it("matches nested paths", () => {
    expect(isActivePath("/users/123", "/users")).toBe(true);
    expect(isActivePath("/usersx", "/users")).toBe(false);
    expect(isActivePath("/users", "/")).toBe(false);
    expect(isActivePath("/", "/")).toBe(true);
  });
});
