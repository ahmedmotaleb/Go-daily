import { describe, expect, it } from "vitest";
import { safeReturnPath, withNotice } from "./notices";

describe("notices", () => {
  it("builds notice URLs", () => {
    expect(withNotice("/drivers/x?created=1", "account_created")).toBe(
      "/drivers/x?notice=account_created",
    );
  });

  it("only allows internal detail pages as return paths", () => {
    const id = "027d3634-3330-4e9c-b8e4-4a41169c17da";
    expect(safeReturnPath(`/drivers/${id}`, "/")).toBe(`/drivers/${id}`);
    expect(safeReturnPath("https://evil.example", "/")).toBe("/");
    expect(safeReturnPath("//evil.example/drivers/x", "/")).toBe("/");
    expect(safeReturnPath(undefined, "/vehicles")).toBe("/vehicles");
  });
});
