import { describe, expect, it } from "vitest";
import { isActivePath, navForPermissions } from "./navigation";

describe("navigation", () => {
  it("hides items without permission", () => {
    const labels = navForPermissions(["vehicles:read"]).map((i) => i.href);
    expect(labels).toContain("/");
    expect(labels).toContain("/vehicles");
    expect(labels).not.toContain("/users");
  });

  it("matches nested paths", () => {
    expect(isActivePath("/users/123", "/users")).toBe(true);
    expect(isActivePath("/usersx", "/users")).toBe(false);
    expect(isActivePath("/users", "/")).toBe(false);
    expect(isActivePath("/", "/")).toBe(true);
  });
});
