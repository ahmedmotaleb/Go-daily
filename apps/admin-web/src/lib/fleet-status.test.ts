import { describe, expect, it } from "vitest";
import { fleetStatus, sinceText } from "@/lib/fleet-status";

describe("fleet status", () => {
  it("maps live tracking states to the design's vehicle states", () => {
    expect(fleetStatus("ONLINE")).toBe("active");
    expect(fleetStatus("STALE")).toBe("stale");
    expect(fleetStatus("OFFLINE")).toBe("critical");
    expect(fleetStatus("NOT_IN_SHIFT")).toBe("inactive");
    expect(fleetStatus(null)).toBe("inactive");
  });

  it("words elapsed time", () => {
    const now = Date.parse("2026-11-04T12:00:00Z");
    expect(sinceText("2026-11-04T11:59:48Z", now)).toBe("منذ 12 ث");
    expect(sinceText("2026-11-04T11:51:00Z", now)).toBe("منذ 9 د");
    expect(sinceText("2026-11-04T10:00:00Z", now)).toBe("منذ 2 س");
    expect(sinceText(null, now)).toBe("—");
  });
});
