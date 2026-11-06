import type { LatLng } from "@/components/map/types";
import type { ShiftTrack } from "@/lib/types";

/** Points further apart than this (seconds) are not joined: the gap is drawn separately. */
export const GAP_SECONDS = 300;

type Point = ShiftTrack["points"][number];

/** Valid points split at gaps: solid segments for the path, dotted links for each gap. */
export function splitTrack(points: Point[]): { segments: LatLng[][]; gaps: LatLng[][] } {
  const valid = points.filter((p) => p.q === "VALID");
  const segments: LatLng[][] = [];
  const gaps: LatLng[][] = [];
  let current: LatLng[] = [];
  let prev: Point | null = null;
  for (const p of valid) {
    const here = { lat: p.lat, lng: p.lng };
    if (prev && (Date.parse(p.t) - Date.parse(prev.t)) / 1000 > GAP_SECONDS) {
      if (current.length > 1) segments.push(current);
      gaps.push([{ lat: prev.lat, lng: prev.lng }, here]);
      current = [];
    }
    current.push(here);
    prev = p;
  }
  if (current.length > 1) segments.push(current);
  return { segments, gaps };
}

/** Position of an instant inside [start, end] as 0-100 (clamped). */
export function pctOf(iso: string, start: string, end: string): number {
  const s = Date.parse(start);
  const e = Date.parse(end);
  if (!(e > s)) return 0;
  return Math.min(100, Math.max(0, ((Date.parse(iso) - s) / (e - s)) * 100));
}

/** Index of the last point at or before `pct` (0-100) of [start, end]; points are in time order. */
export function indexAt(points: { t: string }[], start: string, end: string, pct: number): number {
  const target = Date.parse(start) + ((Date.parse(end) - Date.parse(start)) * pct) / 100;
  let found = 0;
  for (let i = 0; i < points.length; i++) {
    if (Date.parse(points[i]!.t) > target) break;
    found = i;
  }
  return found;
}

/** GPS freshness bar: full when just received, empty after 15 minutes or with no position. */
export function freshnessPct(lastReceived: string | null, now: number = Date.now()): number {
  if (!lastReceived) return 0;
  const seconds = Math.max(0, (now - Date.parse(lastReceived)) / 1000);
  return Math.round(Math.max(0, 100 - (seconds / 900) * 100));
}

/** Milliseconds between replay steps for each speed (points arrive every ~10 s). */
export const SPEED_MS: Record<"1x" | "4x" | "8x", number> = { "1x": 400, "4x": 100, "8x": 50 };
