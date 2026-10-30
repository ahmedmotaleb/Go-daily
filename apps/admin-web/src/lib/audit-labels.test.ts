import { describe, expect, it } from "vitest";
import { actionLabel } from "./audit-labels";

describe("actionLabel", () => {
  it("uses explicit labels first", () => {
    expect(actionLabel("vehicle.created")).toBe("إضافة المركبة");
    expect(actionLabel("attachment.uploaded")).toBe("رفع مرفق");
  });

  it("composes labels for review-lifecycle records", () => {
    expect(actionLabel("maintenance_record.approved")).toBe("اعتماد سجل صيانة");
    expect(actionLabel("fuel_transaction.voided")).toBe("إلغاء سجل وقود");
  });

  it("falls back to the raw code", () => {
    expect(actionLabel("something.odd")).toBe("something.odd");
    expect(actionLabel("expense.exported")).toBe("expense.exported");
  });
});
