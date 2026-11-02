import { describe, expect, it } from "vitest";
import { rateText } from "@/lib/revenue-rates";
import type { RouteRevenueRate } from "@/lib/types";

const base: RouteRevenueRate = {
  id: "r",
  route_id: "x",
  model: "PER_LOOP",
  amount_per_loop: "120.00",
  amount_per_leg: null,
  fare: null,
  passengers_per_leg: null,
  effective_from: "2026-10-01",
  effective_to: null,
  notes: null,
  created_at: "2026-10-01T00:00:00Z",
};

describe("rateText", () => {
  it("describes each model", () => {
    expect(rateText(base)).toContain("لكل دورة");
    expect(rateText(base)).toContain("120");
    expect(rateText({ ...base, model: "PER_LEG", amount_per_leg: "55.50" })).toContain("لكل اتجاه");
    const fare = rateText({
      ...base,
      model: "PASSENGERS_X_FARE",
      fare: "7.50",
      passengers_per_leg: 12,
    });
    expect(fare).toContain("12 راكب");
  });
});
