"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge, type Tone } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type { LivePosition, TrackingState } from "@/lib/types";
import { MapView } from "./map-view";
import type { MapMarker, TileConfig } from "./types";

const POLL_MS = 15_000;

export const STATE_LABELS: Record<TrackingState, string> = {
  ONLINE: "متصل",
  STALE: "تأخر التحديث",
  OFFLINE: "غير متصل",
  NOT_IN_SHIFT: "خارج الوردية",
};
const STATE_TONES: Record<TrackingState, Tone> = {
  ONLINE: "active",
  STALE: "warning",
  OFFLINE: "neutral",
  NOT_IN_SHIFT: "neutral",
};

export function TrackingStateBadge({ state }: { state: TrackingState }) {
  return <Badge tone={STATE_TONES[state]}>{STATE_LABELS[state]}</Badge>;
}

export function LiveFleetMap({
  tiles,
  initial,
  height = 460,
  compact = false,
}: {
  tiles: TileConfig;
  initial: LivePosition[];
  height?: number;
  compact?: boolean;
}) {
  const [positions, setPositions] = useState(initial);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/bff/tracking/live", { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as LivePosition[];
        if (active) {
          setPositions(data);
          setUpdatedAt(new Date().toISOString());
          setError(false);
        }
      } catch {
        if (active) setError(true);
      }
    };
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const markers = useMemo<MapMarker[]>(
    () =>
      positions
        .filter((p) => p.latitude !== null && p.longitude !== null)
        .map((p) => ({
          id: p.vehicle_id,
          position: { lat: p.latitude as number, lng: p.longitude as number },
          tone: p.state === "ONLINE" ? "online" : p.state === "STALE" ? "stale" : "offline",
          heading: p.heading_deg,
          label: `${p.vehicle_code} — ${p.driver_name}`,
          details: [
            STATE_LABELS[p.state],
            p.current_operation ?? "بدون تشغيل محدد",
            p.speed_kmh !== null ? `السرعة: ${p.speed_kmh} كم/س` : "",
            `آخر نقطة: ${formatDateTime(p.last_recorded_at)}`,
          ].filter(Boolean),
        })),
    [positions],
  );
  const withoutFix = positions.filter((p) => p.latitude === null);

  return (
    <div className="space-y-3">
      <MapView tiles={tiles} markers={markers} height={height} />
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
        <span>
          {positions.length} وردية نشطة · {markers.length} على الخريطة
          {updatedAt ? ` · آخر تحديث ${formatDateTime(updatedAt)}` : ""}
        </span>
        {error ? (
          <span className="text-danger">تعذر تحديث المواقع، سيتم إعادة المحاولة</span>
        ) : null}
      </div>
      {!compact && positions.length > 0 ? (
        <ul className="divide-y divide-line rounded-[var(--radius-card)] border border-line bg-surface">
          {positions.map((p) => (
            <li
              key={p.shift_id}
              className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm"
            >
              <span>
                <Link
                  href={`/shifts/${p.shift_id}`}
                  className="font-semibold text-forest-700 hover:underline"
                >
                  <span className="ltr-nums">{p.vehicle_code}</span> — {p.driver_name}
                </Link>
                <span className="ms-2 text-xs text-ink-muted">
                  {p.current_operation ?? "بدون تشغيل محدد"}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <span className="text-xs text-ink-muted">{formatDateTime(p.last_recorded_at)}</span>
                <TrackingStateBadge state={p.state} />
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {withoutFix.length > 0 ? (
        <p className="text-xs text-warning">
          {withoutFix.length} وردية نشطة بدون أي موقع مستلم بعد:{" "}
          {withoutFix.map((p) => p.vehicle_code).join("، ")}
        </p>
      ) : null}
    </div>
  );
}
