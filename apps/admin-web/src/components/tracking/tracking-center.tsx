"use client";

import clsx from "clsx";
import { Check, Pause, Play, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { MapView } from "@/components/map/map-view";
import type { LatLng, MapMarker, MapPolyline, TileConfig } from "@/components/map/types";
import { Badge } from "@/components/ui/badge";
import { FLEET_STATUS, fleetStatus, sinceText, type FleetStatus } from "@/lib/fleet-status";
import { formatNumber } from "@/lib/format";
import { freshnessPct, indexAt, pctOf, SPEED_MS, splitTrack } from "@/lib/track-replay";
import type { LivePosition, Shift, ShiftTrack } from "@/lib/types";

const TIME = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const hhmm = (iso: string | null) => (iso ? TIME.format(new Date(iso)) : "—");

export type ListRow = {
  key: string;
  vehicleId: string;
  /** Null when there is nothing to show for this row (a vehicle with no shift). */
  href: string | null;
  plate: string;
  driver: string;
  operation: string;
  status: FleetStatus;
  lastReceived: string | null;
  selected: boolean;
};

export type SelectedShift = { shift: Shift; track: ShiftTrack; expected: LatLng[] };

type Filter = "all" | "active" | "attention" | "inactive";
const FILTERS: { id: Filter; label: string; match: (s: FleetStatus) => boolean }[] = [
  { id: "all", label: "الكل", match: () => true },
  { id: "active", label: "نشطة", match: (s) => s === "active" },
  { id: "attention", label: "تحتاج انتباه", match: (s) => s === "stale" || s === "critical" },
  { id: "inactive", label: "غير نشطة", match: (s) => s === "inactive" },
];

function duration(minutes: number | null): string {
  if (minutes === null) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} س ${m} د` : `${m} د`;
}

const TIMELINE_DOT: Record<string, string> = {
  SHIFT_STARTED: "bg-forest-800 border-forest-800",
  SHIFT_ENDED: "bg-forest-800 border-forest-800",
  SESSION_STARTED: "bg-lime-400 border-forest-800",
  SESSION_ENDED: "bg-lime-400 border-forest-800",
  STOP: "bg-surface border-forest-800",
  GAP: "bg-red-400 border-red-400",
  DEVICE_EVENT: "bg-neutral-400 border-neutral-400",
};

export function TrackingCenter({
  mode,
  rows: initialRows,
  selected,
  live: initialLive,
  tiles,
}: {
  mode: "live" | "replay";
  rows: ListRow[];
  selected: SelectedShift | null;
  live: LivePosition[];
  tiles: TileConfig;
}) {
  const [live, setLive] = useState(initialLive);
  const [now, setNow] = useState(() => Date.now());
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const router = useRouter();
  // Live mode: the selected shift's path and timeline are reloaded every minute.
  useEffect(() => {
    if (mode !== "live" || !selected) return;
    const id = window.setInterval(() => router.refresh(), 60_000);
    return () => window.clearInterval(id);
  }, [mode, selected, router]);

  // Live mode: refresh positions every 15 s.
  useEffect(() => {
    if (mode !== "live") return;
    let active = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/bff/tracking/live", { cache: "no-store" });
        if (res.ok && active) setLive((await res.json()) as LivePosition[]);
      } catch {
        // keep the last positions; the freshness bars show their age
      }
      if (active) setNow(Date.now());
    };
    const id = window.setInterval(tick, 15_000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [mode]);

  const rows = useMemo(() => {
    if (mode !== "live") return initialRows;
    const byVehicle = new Map(live.map((p) => [p.vehicle_id, p]));
    return initialRows.map((r) => {
      const p = byVehicle.get(r.vehicleId);
      return p ? { ...r, status: fleetStatus(p.state), lastReceived: p.last_received_at } : r;
    });
  }, [mode, initialRows, live]);

  const visible = rows.filter(
    (r) =>
      FILTERS.find((f) => f.id === filter)!.match(r.status) &&
      (!query.trim() || `${r.plate} ${r.driver}`.includes(query.trim())),
  );

  // --- Replay --------------------------------------------------------------
  const points = useMemo(
    () => (selected ? selected.track.points.filter((p) => p.q === "VALID") : []),
    [selected],
  );
  // Live follows the latest point; replay starts from the beginning of the shift.
  const startAt = mode === "live" && points.length ? points.length - 1 : 0;
  const [index, setIndex] = useState(startAt);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<keyof typeof SPEED_MS>("4x");
  const [loaded, setLoaded] = useState(points);
  if (loaded !== points) {
    // A new shift (or a refreshed track): reset the replay during render, not in an effect.
    setLoaded(points);
    setIndex(startAt);
    setPlaying(false);
  }
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setIndex((i) => {
        if (i >= points.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, SPEED_MS[speed]);
    return () => window.clearInterval(id);
  }, [playing, speed, points.length]);

  const current = points[index] ?? null;
  const split = useMemo(() => (selected ? splitTrack(selected.track.points) : null), [selected]);
  const polylines = useMemo<MapPolyline[]>(() => {
    if (!selected || !split) return [];
    return [
      ...(selected.expected.length > 1
        ? [{ id: "expected", points: selected.expected, tone: "faded" as const }]
        : []),
      ...split.segments.map((points, i) => ({ id: `seg-${i}`, points, tone: "track" as const })),
      ...split.gaps.map((points, i) => ({ id: `gap-${i}`, points, tone: "gap" as const })),
    ];
  }, [selected, split]);

  const markers = useMemo<MapMarker[]>(() => {
    const out: MapMarker[] = [];
    if (mode === "live") {
      for (const p of live) {
        if (p.latitude === null || p.longitude === null) continue;
        const s = fleetStatus(p.state);
        out.push({
          id: p.vehicle_id,
          position: { lat: p.latitude, lng: p.longitude },
          tone: s === "active" ? "online" : s === "stale" ? "stale" : "offline",
          heading: p.heading_deg,
          label: `${p.plate_number} — ${p.driver_name}`,
          details: [FLEET_STATUS[s].label, p.current_operation ?? "بدون تشغيل محدد"],
        });
      }
    }
    if (selected) {
      selected.track.stops.forEach((s, i) =>
        out.push({
          id: `stop-${i}`,
          position: { lat: s.latitude, lng: s.longitude },
          tone: "stop",
          label: `توقف ${i + 1}`,
          details: [`${hhmm(s.start)} – ${hhmm(s.end)}`, `${Math.round(s.seconds / 60)} دقيقة`],
        }),
      );
      if (current && mode === "replay") {
        out.push({
          id: "replay",
          position: { lat: current.lat, lng: current.lng },
          tone: "replay",
          label: "الموضع في الإعادة",
          details: [
            hhmm(current.t),
            current.spd !== null ? `${Math.round(current.spd * 3.6)} كم/س` : "",
          ],
        });
      }
    }
    return out;
  }, [mode, live, selected, current]);

  const fitTo =
    selected && points.length ? points.map((p) => ({ lat: p.lat, lng: p.lng })) : undefined;
  const windowStart = selected?.track.window_start ?? null;
  const windowEnd = selected?.track.window_end ?? null;
  const counts = Object.fromEntries(
    FILTERS.map((f) => [f.id, rows.filter((r) => f.match(r.status)).length]),
  ) as Record<Filter, number>;

  return (
    <div className="flex flex-1 flex-wrap items-stretch min-[1180px]:h-[calc(100dvh-68px)] min-[1180px]:flex-nowrap">
      {/* Vehicle list */}
      <aside
        aria-label={mode === "live" ? "قائمة السيارات" : "ورديات اليوم"}
        className="flex flex-[1_1_290px] flex-col border-line bg-surface min-[1180px]:border-l"
      >
        <div className="flex flex-col gap-3 border-b border-line p-4">
          <label className="flex h-11 items-center gap-2 rounded-[var(--radius-control)] border border-line bg-neutral-50 px-3">
            <Search className="size-[18px] text-ink-muted" strokeWidth={1.8} aria-hidden="true" />
            <span className="sr-only">بحث في السيارات</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="لوحة أو سائق"
              className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none focus-visible:shadow-none"
            />
          </label>
          <div role="group" aria-label="تصفية" className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                aria-pressed={filter === f.id}
                onClick={() => setFilter(f.id)}
                className={clsx(
                  "rounded-full border px-3 py-1.5 text-xs font-semibold",
                  filter === f.id
                    ? "border-forest-800 bg-forest-800 text-white"
                    : "border-line bg-surface text-ink hover:bg-neutral-50",
                )}
              >
                {f.label} <span className="ltr-nums">{counts[f.id]}</span>
              </button>
            ))}
          </div>
        </div>
        <ul className="max-h-[420px] min-h-0 flex-1 overflow-y-auto min-[1180px]:max-h-none">
          {visible.length === 0 ? (
            <li className="px-4 py-6 text-sm text-ink-muted">
              {mode === "live" ? "لا توجد سيارات مطابقة." : "لا توجد ورديات في هذا اليوم."}
            </li>
          ) : null}
          {visible.map((r) => {
            const s = FLEET_STATUS[r.status];
            const fresh = mode === "live" ? freshnessPct(r.lastReceived, now) : null;
            return (
              <li key={r.key}>
                <RowShell row={r}>
                  <span
                    aria-hidden="true"
                    className={clsx("mt-1 size-3 shrink-0 rounded-full", s.dot)}
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="flex justify-between gap-2">
                      <span className="text-sm font-bold">{r.plate}</span>
                      <span className="text-[11px] text-ink-muted">
                        {mode === "live" ? sinceText(r.lastReceived, now) : ""}
                      </span>
                    </span>
                    <span className="truncate text-xs text-ink-soft">
                      {r.driver} · {r.operation}
                    </span>
                    {fresh !== null && r.lastReceived ? (
                      <span className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                        <span
                          aria-hidden="true"
                          className="block h-1 w-14 overflow-hidden rounded-full bg-neutral-100"
                        >
                          <span
                            className={clsx(
                              "block h-full rounded-full",
                              r.status === "active"
                                ? "bg-forest-800"
                                : r.status === "stale"
                                  ? "bg-amber-400"
                                  : "bg-red-400",
                            )}
                            style={{ width: `${fresh}%` }}
                          />
                        </span>
                        حداثة GPS
                      </span>
                    ) : null}
                  </span>
                </RowShell>
              </li>
            );
          })}
        </ul>
        <p className="border-t border-line px-4 py-3 text-[11px] leading-5 text-ink-muted">
          تُسجل المواقع أثناء ورديات العمل فقط. انقطاع الإشارة لا يعني بالضرورة وجود مشكلة — راجع
          الخط الزمني للوردية.
        </p>
      </aside>

      {/* Map + replay */}
      <section
        aria-label="الخريطة وإعادة المسار"
        className="flex min-w-0 flex-[999_1_520px] flex-col"
      >
        <div className="relative min-h-[420px] flex-1 bg-[#e8eee9] sm:min-h-[560px]">
          <div className="absolute inset-0">
            <MapView
              tiles={tiles}
              markers={markers}
              polylines={polylines}
              fitTo={fitTo}
              height="100%"
              flush
            />
          </div>
          {selected ? (
            <ul
              aria-label="دلالة الخطوط"
              className="absolute top-4 right-4 z-[500] flex flex-col gap-2 rounded-[14px] border border-line bg-surface px-3.5 py-3 text-xs shadow-[0_6px_18px_rgb(8_43_36/0.10)]"
            >
              <li className="flex items-center gap-2">
                <span aria-hidden="true" className="h-[5px] w-[26px] rounded-full bg-forest-800" />
                المسار الفعلي
              </li>
              {selected.expected.length > 1 ? (
                <li className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="w-[26px] border-t-[3px] border-dashed border-neutral-500"
                  />
                  المسار المتوقع (خطوط بين المحطات)
                </li>
              ) : null}
              <li className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="w-[26px] border-t-[3px] border-dotted border-red-400"
                />
                انقطاع التتبع
              </li>
              <li className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="mx-1.5 size-3.5 rounded-full border-2 border-forest-800"
                />
                محطة توقف
              </li>
            </ul>
          ) : null}
        </div>

        {selected && points.length > 1 && windowStart && windowEnd ? (
          <div className="flex flex-wrap items-center gap-4 border-t border-line bg-surface px-5 py-3.5">
            <button
              type="button"
              onClick={() => {
                if (index >= points.length - 1) setIndex(0);
                setPlaying((p) => !p);
              }}
              aria-label={playing ? "إيقاف مؤقت" : "تشغيل"}
              className="flex size-[52px] shrink-0 items-center justify-center rounded-full bg-forest-800 text-lime-400 hover:bg-forest-900"
            >
              {playing ? (
                <Pause className="size-[22px] fill-current" />
              ) : (
                <Play className="size-[22px] fill-current" />
              )}
            </button>
            <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1.5">
              <div className="flex justify-between text-xs text-ink-muted">
                <span>{hhmm(windowStart)}</span>
                <span className="font-bold text-primary">{hhmm(current?.t ?? null)}</span>
                <span>{hhmm(windowEnd)}</span>
              </div>
              <div className="relative h-[22px]">
                <div
                  className="absolute inset-x-0 top-1.5 h-2.5 rounded-full bg-neutral-100"
                  aria-hidden="true"
                >
                  <div
                    className="absolute inset-y-0 right-0 rounded-full bg-forest-800"
                    style={{ width: current ? `${pctOf(current.t, windowStart, windowEnd)}%` : 0 }}
                  />
                  {selected.track.gaps.map((g) => (
                    <div
                      key={g.start}
                      className="absolute -inset-y-0.5 rounded-[3px] bg-red-400"
                      style={{
                        right: `${pctOf(g.start, windowStart, windowEnd)}%`,
                        width: `${Math.max(0.8, pctOf(g.end, windowStart, windowEnd) - pctOf(g.start, windowStart, windowEnd))}%`,
                      }}
                    />
                  ))}
                  {selected.track.stops.map((s) => (
                    <div
                      key={s.start}
                      className="absolute -top-1 h-[18px] w-1 rounded-sm bg-ink"
                      style={{ right: `${pctOf(s.start, windowStart, windowEnd)}%` }}
                    />
                  ))}
                </div>
                <input
                  type="range"
                  min={0}
                  max={1000}
                  value={current ? Math.round(pctOf(current.t, windowStart, windowEnd) * 10) : 0}
                  onChange={(e) =>
                    setIndex(indexAt(points, windowStart, windowEnd, Number(e.target.value) / 10))
                  }
                  aria-label="موضع إعادة المسار"
                  aria-valuetext={hhmm(current?.t ?? null)}
                  dir="rtl"
                  className={clsx(
                    "absolute inset-0 w-full cursor-pointer appearance-none bg-transparent",
                    "[&::-webkit-slider-thumb]:size-[22px] [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-[3px] [&::-webkit-slider-thumb]:border-forest-800 [&::-webkit-slider-thumb]:bg-lime-400 [&::-webkit-slider-thumb]:shadow-[0_2px_6px_rgb(8_43_36/0.3)]",
                    "[&::-moz-range-thumb]:size-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-[3px] [&::-moz-range-thumb]:border-forest-800 [&::-moz-range-thumb]:bg-lime-400",
                  )}
                />
              </div>
              <div className="flex gap-3.5 text-[11px] text-ink-muted">
                <span className="flex items-center gap-1">
                  <span aria-hidden="true" className="h-2.5 w-[3px] rounded-[1px] bg-ink" />
                  توقف
                </span>
                <span className="flex items-center gap-1">
                  <span aria-hidden="true" className="h-1.5 w-2.5 rounded-sm bg-red-400" />
                  انقطاع
                </span>
              </div>
            </div>
            <div
              role="group"
              aria-label="سرعة العرض"
              className="flex gap-1 rounded-[var(--radius-control)] border border-line bg-neutral-50 p-1"
            >
              {(Object.keys(SPEED_MS) as (keyof typeof SPEED_MS)[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={speed === s}
                  onClick={() => setSpeed(s)}
                  className={clsx(
                    "ltr-nums h-9 min-w-11 rounded-lg text-[13px] font-bold",
                    speed === s ? "bg-forest-800 text-white" : "text-ink-soft hover:bg-surface",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      {/* Detail panel */}
      <aside
        aria-label="تفاصيل الوردية"
        className="flex flex-[1_1_330px] flex-col gap-4 overflow-y-auto border-line bg-surface p-5 min-[1180px]:border-r"
      >
        {selected ? (
          <ShiftDetail selected={selected} />
        ) : (
          <p className="text-sm text-ink-muted">
            {mode === "live"
              ? "اختر سيارة في وردية من القائمة لعرض مسارها وتفاصيلها."
              : "اختر وردية من القائمة لإعادة مسارها."}
          </p>
        )}
      </aside>
    </div>
  );
}

function RowShell({ row, children }: { row: ListRow; children: ReactNode }) {
  const cls = clsx(
    "flex items-start gap-3 border-b border-neutral-100 px-4 py-3.5",
    row.selected ? "bg-[#f1f6ec] shadow-[inset_-3px_0_0_var(--color-lime-400)]" : "",
    row.href && !row.selected ? "hover:bg-neutral-50" : "",
  );
  return row.href ? (
    <Link href={row.href} aria-current={row.selected ? "true" : undefined} className={cls}>
      {children}
    </Link>
  ) : (
    <div className={cls}>{children}</div>
  );
}

function ShiftDetail({ selected }: { selected: SelectedShift }) {
  const { shift, track } = selected;
  const rec = track.odometer_reconciliation;
  const op = shift.active_session ?? shift.sessions[shift.sessions.length - 1] ?? null;
  const active = shift.status === "ACTIVE";
  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xl font-bold">{shift.vehicle.plate_number}</span>
          <span className="text-[13px] text-ink-soft">
            {shift.driver.full_name}
            {op ? ` · ${op.operation_type.name_ar}${op.route ? ` — ${op.route.name}` : ""}` : ""}
          </span>
        </div>
        <Badge tone={active ? "success" : "neutral"}>
          {active ? "الوردية نشطة" : "الوردية منتهية"}
        </Badge>
      </div>
      <dl className="grid grid-cols-2 gap-2.5">
        {[
          ["بداية الوردية", hhmm(shift.started_at)],
          ["مدة التشغيل", duration(shift.duration_minutes)],
          ["مسافة GPS", `${formatNumber(track.gps_distance_km)} كم`],
          [
            "مسافة العداد",
            track.odometer_distance_km === null
              ? "—"
              : `${formatNumber(track.odometer_distance_km)} كم`,
          ],
        ].map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5 rounded-[14px] bg-neutral-50 p-3">
            <dt className="text-[11px] text-ink-muted">{k}</dt>
            <dd className="text-base font-bold">{v}</dd>
          </div>
        ))}
      </dl>
      {rec.status === "WITHIN_TOLERANCE" ? (
        <p className="flex items-center gap-2.5 rounded-[var(--radius-control)] bg-success-soft px-3 py-2.5 text-[13px] text-success">
          <Check className="size-[18px] shrink-0" strokeWidth={2.2} aria-hidden="true" />
          الفرق {formatNumber(rec.abs_difference_km)} كم ({formatNumber(rec.difference_pct)}٪) — ضمن
          الحد المسموح
        </p>
      ) : rec.status === "REVIEW" ? (
        <p className="rounded-[var(--radius-control)] bg-warning-soft px-3 py-2.5 text-[13px] text-warning">
          فرق {formatNumber(rec.abs_difference_km)} كم بين العداد وGPS — مراجعة مطلوبة
        </p>
      ) : rec.status === "NOT_COMPLETED" ? (
        <p className="rounded-[var(--radius-control)] bg-neutral-50 px-3 py-2.5 text-[13px] text-ink-muted">
          مقارنة العداد مع GPS تتم بعد انتهاء الوردية.
        </p>
      ) : (
        <p className="rounded-[var(--radius-control)] bg-neutral-50 px-3 py-2.5 text-[13px] text-ink-muted">
          {rec.status === "MISSING_ODOMETER"
            ? "قراءة العداد ناقصة؛ لا تتم المقارنة."
            : "تغطية GPS غير كافية للمقارنة مع العداد."}
        </p>
      )}

      <div className="flex flex-col">
        <h2 className="mb-2 text-[15px] font-bold">الخط الزمني للوردية</h2>
        {track.timeline.length === 0 ? (
          <p className="text-sm text-ink-muted">لا توجد أحداث بعد.</p>
        ) : (
          <ol>
            {track.timeline.map((t, i) => (
              <li key={`${t.at}-${i}`} className="flex items-stretch gap-3">
                <span className="flex w-4 flex-col items-center" aria-hidden="true">
                  <span
                    className={clsx(
                      "mt-1 size-3 shrink-0 rounded-full border-2",
                      TIMELINE_DOT[t.kind] ?? "border-neutral-400 bg-neutral-400",
                    )}
                  />
                  <span
                    className={clsx(
                      "w-0.5 flex-1",
                      i === track.timeline.length - 1 ? "bg-transparent" : "bg-line",
                    )}
                  />
                </span>
                <span className="flex flex-1 flex-col gap-0.5 pb-3.5">
                  <span className="flex justify-between gap-2">
                    <span className="text-sm font-semibold">{t.label}</span>
                    <span className="ltr-nums text-xs text-ink-muted">{hhmm(t.at)}</span>
                  </span>
                  {t.until ? (
                    <span
                      className={clsx(
                        "text-xs",
                        t.kind === "GAP" ? "text-danger" : "text-ink-muted",
                      )}
                    >
                      حتى {hhmm(t.until)}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="mt-auto flex flex-col gap-2">
        <Link
          href={`/shifts/${shift.id}`}
          className="flex h-[46px] items-center justify-center rounded-[var(--radius-control)] bg-primary text-sm font-semibold text-white hover:bg-primary-hover"
        >
          تفاصيل الوردية
        </Link>
        <Link
          href={`/exceptions?shift_id=${shift.id}`}
          className="flex h-[46px] items-center justify-center rounded-[var(--radius-control)] border border-line text-sm font-semibold text-primary hover:bg-neutral-50"
        >
          حالات المراجعة لهذه الوردية
        </Link>
      </div>
    </>
  );
}
