import { describe, expect, it } from "vitest";
import { freshnessPct, indexAt, pctOf, splitTrack } from "@/lib/track-replay";

const p = (t: string, lat: number, q = "VALID") => ({ t, lat, lng: 31, acc: 5, spd: 0, q });

describe("track replay helpers", () => {
  it("splits the path at gaps and never joins across them", () => {
    const { segments, gaps } = splitTrack([
      p("2026-11-04T07:00:00Z", 30.0),
      p("2026-11-04T07:00:10Z", 30.1),
      p("2026-11-04T07:00:20Z", 30.9, "IMPLAUSIBLE_SPEED"), // not drawn
      p("2026-11-04T07:10:00Z", 30.2), // 10 min later: a gap
      p("2026-11-04T07:10:10Z", 30.3),
    ]);
    expect(segments).toHaveLength(2);
    expect(gaps).toEqual([
      [
        { lat: 30.1, lng: 31 },
        { lat: 30.2, lng: 31 },
      ],
    ]);
  });

  it("places instants on the timeline and measures freshness", () => {
    expect(pctOf("2026-11-04T08:00:00Z", "2026-11-04T07:00:00Z", "2026-11-04T09:00:00Z")).toBe(50);
    expect(pctOf("2026-11-04T06:00:00Z", "2026-11-04T07:00:00Z", "2026-11-04T09:00:00Z")).toBe(0);
    const now = Date.parse("2026-11-04T12:00:00Z");
    expect(freshnessPct("2026-11-04T12:00:00Z", now)).toBe(100);
    expect(freshnessPct("2026-11-04T11:52:30Z", now)).toBe(50);
    expect(freshnessPct("2026-11-04T11:00:00Z", now)).toBe(0);
    expect(freshnessPct(null, now)).toBe(0);
  });

  it("maps a slider position to the last point at or before that time", () => {
    const pts = [
      p("2026-11-04T07:00:00Z", 30.0),
      p("2026-11-04T07:10:00Z", 30.1),
      p("2026-11-04T08:50:00Z", 30.2), // after a long gap
    ];
    const [start, end] = ["2026-11-04T07:00:00Z", "2026-11-04T09:00:00Z"];
    expect(indexAt(pts, start, end, 0)).toBe(0);
    expect(indexAt(pts, start, end, 50)).toBe(1); // inside the gap: stays on the last point
    expect(indexAt(pts, start, end, 100)).toBe(2);
  });
});
