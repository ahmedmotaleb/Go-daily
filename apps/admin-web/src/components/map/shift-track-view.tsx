"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { ShiftTrack } from "@/lib/types";
import { MapView } from "./map-view";
import type { LatLng, MapMarker, TileConfig } from "./types";

const QUALITY_LABELS: Record<string, string> = {
  VALID: "صالحة",
  LOW_ACCURACY: "دقة منخفضة",
  IMPLAUSIBLE_SPEED: "قفزة غير منطقية",
  MOCK: "موقع وهمي من الجهاز",
};

export function ShiftTrackView({ tiles, track }: { tiles: TileConfig; track: ShiftTrack }) {
  const valid = useMemo(() => track.points.filter((p) => p.q === "VALID"), [track.points]);
  const path = useMemo<LatLng[]>(() => valid.map((p) => ({ lat: p.lat, lng: p.lng })), [valid]);
  const [index, setIndex] = useState(valid.length ? valid.length - 1 : 0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setIndex((i) => {
        if (i >= valid.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 150);
    return () => window.clearInterval(id);
  }, [playing, valid.length]);

  const current = valid[index];
  const markers = useMemo<MapMarker[]>(() => {
    const out: MapMarker[] = [];
    if (valid.length) {
      const first = valid[0]!;
      const last = valid[valid.length - 1]!;
      out.push({
        id: "start",
        position: { lat: first.lat, lng: first.lng },
        tone: "start",
        label: "أول نقطة",
        details: [formatDateTime(first.t)],
      });
      out.push({
        id: "end",
        position: { lat: last.lat, lng: last.lng },
        tone: "end",
        label: "آخر نقطة",
        details: [formatDateTime(last.t)],
      });
    }
    track.stops.forEach((s, i) =>
      out.push({
        id: `stop-${i}`,
        position: { lat: s.latitude, lng: s.longitude },
        tone: "stop",
        label: `توقف ${Math.round(s.seconds / 60)} دقيقة`,
        details: [`${formatDateTime(s.start)} ← ${formatDateTime(s.end)}`],
      }),
    );
    if (current) {
      out.push({
        id: "replay",
        position: { lat: current.lat, lng: current.lng },
        tone: "replay",
        label: "الموضع في الإعادة",
        details: [
          formatDateTime(current.t),
          current.spd !== null ? `${Math.round(current.spd * 3.6)} كم/س` : "",
        ],
      });
    }
    return out;
  }, [valid, track.stops, current]);

  if (track.points.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        لا توجد نقاط GPS مسجلة لهذه الوردية. لم يتم إنشاء أي مسار تقديري.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-[var(--radius-control)] bg-lime-50 p-3">
          <p className="text-xs text-ink-muted">المسافة حسب GPS</p>
          <p className="ltr-nums text-lg font-bold">{formatNumber(track.gps_distance_km)} كم</p>
          <p className="text-[11px] text-ink-muted">من النقاط الصالحة المتتالية فقط</p>
        </div>
        <div className="rounded-[var(--radius-control)] bg-neutral-100 p-3">
          <p className="text-xs text-ink-muted">المسافة حسب العداد</p>
          <p className="ltr-nums text-lg font-bold">
            {track.odometer_distance_km === null
              ? "—"
              : `${formatNumber(track.odometer_distance_km)} كم`}
          </p>
          <p className="text-[11px] text-ink-muted">من قراءات السائق</p>
        </div>
        <div className="rounded-[var(--radius-control)] bg-neutral-100 p-3">
          <p className="text-xs text-ink-muted">نقاط GPS</p>
          <p className="ltr-nums text-lg font-bold">{formatNumber(track.points.length)}</p>
          <p className="text-[11px] text-ink-muted">
            {Object.entries(track.counts)
              .filter(([q, n]) => q !== "VALID" && n > 0)
              .map(([q, n]) => `${QUALITY_LABELS[q] ?? q}: ${n}`)
              .join(" · ") || "كلها صالحة"}
          </p>
        </div>
        <div className="rounded-[var(--radius-control)] bg-neutral-100 p-3">
          <p className="text-xs text-ink-muted">انقطاعات البيانات</p>
          <p className="ltr-nums text-lg font-bold">{track.gaps.length}</p>
          <p className="text-[11px] text-ink-muted">لا يتم ملء الانقطاعات بنقاط تقديرية</p>
        </div>
      </div>

      <MapView
        tiles={tiles}
        polylines={[{ id: "track", points: path, tone: "track" }]}
        markers={markers}
        fitTo={path}
        height={440}
      />

      {valid.length > 1 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-[var(--radius-control)] border border-line p-3">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              if (index >= valid.length - 1) setIndex(0);
              setPlaying((p) => !p);
            }}
            aria-label={playing ? "إيقاف الإعادة" : "تشغيل الإعادة"}
          >
            {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
            {playing ? "إيقاف" : "إعادة المسار"}
          </Button>
          <input
            type="range"
            min={0}
            max={valid.length - 1}
            value={index}
            onChange={(e) => {
              setPlaying(false);
              setIndex(Number(e.target.value));
            }}
            className="min-w-48 flex-1 accent-forest-700"
            aria-label="موضع الإعادة"
          />
          <span className="ltr-nums text-xs text-ink-muted">
            {current ? formatDateTime(current.t) : ""}
          </span>
        </div>
      ) : null}

      {track.gaps.length > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-semibold">انقطاعات بيانات GPS</h3>
          <ul className="space-y-1 text-sm">
            {track.gaps.map((g) => (
              <li key={g.start} className="text-ink-muted">
                {formatDateTime(g.start)} ← {formatDateTime(g.end)} ({Math.round(g.seconds / 60)}{" "}
                دقيقة)
                {g.displacement_m !== null
                  ? ` · إزاحة مستقيمة ${formatNumber(Math.round(g.displacement_m))} م (غير محسوبة في المسافة)`
                  : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h3 className="mb-2 text-sm font-semibold">الخط الزمني</h3>
        <ol className="space-y-1.5 border-s-2 border-line ps-4 text-sm">
          {track.timeline.map((t, i) => (
            <li key={`${t.at}-${i}`} className={t.kind === "GAP" ? "text-warning" : undefined}>
              <span className="ltr-nums text-xs text-ink-muted">{formatDateTime(t.at)}</span> —{" "}
              {t.label}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
