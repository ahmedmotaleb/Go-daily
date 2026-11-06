import { describe, expect, it } from "vitest";
import { formKey } from "./forms";

describe("formKey", () => {
  it("changes when submitted values change so the form remounts with them", () => {
    expect(formKey({})).toBe(formKey({}));
    expect(formKey({ values: { role: "OPERATIONS" } })).not.toBe(formKey({}));
    expect(formKey({}, "v1")).not.toBe(formKey({}, "v2"));
  });
});
