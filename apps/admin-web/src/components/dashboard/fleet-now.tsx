"use client";

import clsx from "clsx";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { MapView } from "@/components/map/map-view";
import type { MapMarker, TileConfig } from "@/components/map/types";
import { Badge } from "@/components/ui/badge";
import { FLEET_STATUS, fleetStatus, sinceText, type FleetStatus } from "@/lib/fleet-status";
import type { DashboardSummary, LivePosition } from "@/lib/types";

const POLL_MS = 15_000;

type Row = {
  id: string;
  code: string;
  plate: string;
  type: string;
  driver: string | null;
  operation: string | null;
  status: FleetStatus;
  live: LivePosition | null;
};

function rows(vehicles: DashboardSummary["vehicles"], live: LivePosition[]): Row[] {
  const byVehicle = new Map(live.map((p) => [p.vehicle_id, p]));
  const order: Record<FleetStatus, number> = { critical: 0, stale: 1, active: 2, inactive: 3 };
  return vehicles
    .map((v) => {
      const p = byVehicle.get(v.id) ?? null;
      return {
        id: v.id,
        code: v.internal_code,
        plate: v.plate_number,
        type: v.vehicle_type,
        driver: p?.driver_name ?? v.driver_name,
        operation: p?.current_operation ?? v.current_operation,
        status: fleetStatus(p ? p.state : null),
        live: p,
      };
    })
    .sort((a, b) => order[a.status] - order[b.status] || a.code.localeCompare(b.code));
}

function Dot({ status }: { status: FleetStatus }) {
  return (
    <span
      aria-hidden="true"
      className={clsx("size-3 shrink-0 rounded-full", FLEET_STATUS[status].dot)}
    />
  );
}

/** "الأسطول الآن": live map, vehicle list and the selected vehicle's card. */
export function FleetNow({
  tiles,
  vehicles,
  initial,
}: {
  tiles: TileConfig;
  vehicles: DashboardSummary["vehicles"];
  initial: LivePosition[];
}) {
  const [live, setLive] = useState(initial);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const list = useMemo(() => rows(vehicles, live), [vehicles, live]);
  const [selectedId, setSelectedId] = useState<string | null>(list[0]?.id ?? null);
  const selected = list.find((r) => r.id === selectedId) ?? list[0] ?? null;

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/bff/tracking/live", { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as LivePosition[];
        if (active) {
          setLive(data);
          setError(false);
        }
      } catch {
        if (active) setError(true);
      }
      if (active) setNow(Date.now());
    };
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const markers = useMemo<MapMarker[]>(
    () =>
      list
        .filter((r) => r.live && r.live.latitude !== null && r.live.longitude !== null)
        .map((r) => ({
          id: r.id,
          position: { lat: r.live!.latitude as number, lng: r.live!.longitude as number },
          tone: r.status === "active" ? "online" : r.status === "stale" ? "stale" : "offline",
          heading: r.live!.heading_deg,
          label: `${r.plate} — ${r.driver ?? "بدون سائق"}`,
          details: [FLEET_STATUS[r.status].label, r.operation ?? "بدون تشغيل محدد"],
        })),
    [list],
  );
  const focus =
    selected?.live && selected.live.latitude !== null && selected.live.longitude !== null
      ? { lat: selected.live.latitude, lng: selected.live.longitude }
      : null;
  const counts = list.reduce<Record<FleetStatus, number>>(
    (acc, r) => ({ ...acc, [r.status]: acc[r.status] + 1 }),
    { active: 0, stale: 0, critical: 0, inactive: 0 },
  );

  return (
    <section
      aria-label="خريطة الأسطول المباشرة"
      className="flex min-w-0 flex-col overflow-hidden rounded-[var(--radius-panel)] border border-line bg-surface shadow-[var(--shadow-panel)]"
    >
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-4">
        <div className="flex flex-[1_1_200px] items-center gap-2.5">
          <span
            aria-hidden="true"
            className="size-2.5 rounded-full bg-lime-400 shadow-[0_0_0_4px_rgb(181_227_61/0.28)]"
          />
          <h2 className="text-[17px] font-bold whitespace-nowrap">الأسطول الآن</h2>
          <span className="text-[13px] text-ink-muted">
            {list.length} سيارة · تحديث كل 15 ثانية
          </span>
        </div>
        <ul className="flex flex-wrap gap-3.5 text-xs text-ink-soft" aria-label="دلالة الألوان">
          {(Object.keys(FLEET_STATUS) as FleetStatus[]).map((s) => (
            <li key={s} className="flex items-center gap-1.5">
              <Dot status={s} />
              {FLEET_STATUS[s].label} <span className="ltr-nums">({counts[s]})</span>
            </li>
          ))}
        </ul>
        <Link
          href="/tracking"
          className="rounded-[10px] border border-line px-3 py-2 text-[13px] font-semibold text-primary hover:bg-neutral-50"
        >
          فتح مركز التتبع ←
        </Link>
      </div>

      <div className="flex flex-1 flex-wrap">
        <div className="relative min-h-[460px] min-w-0 flex-[999_1_380px] bg-[#e8eee9]">
          <MapView
            tiles={tiles}
            markers={markers}
            height={460}
            onMarkerClick={setSelectedId}
            focus={focus}
            flush
          />
          {selected ? (
            <div className="absolute bottom-4 left-4 z-[500] flex w-[280px] max-w-[calc(100%-32px)] flex-col gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4 shadow-[var(--shadow-dialog)]">
              <div className="flex items-center justify-between gap-2">
                <div className="flex flex-col gap-0.5">
                  <span className="text-base font-bold">{selected.plate}</span>
                  <span className="text-xs text-ink-muted">{selected.type}</span>
                </div>
                <Badge tone={FLEET_STATUS[selected.status].tone}>
                  {FLEET_STATUS[selected.status].label}
                </Badge>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2.5 text-[13px]">
                <div className="flex flex-col gap-0.5">
                  <dt className="text-[11px] text-ink-muted">السائق</dt>
                  <dd className="font-semibold">{selected.driver ?? "بدون سائق"}</dd>
                </div>
                <div className="flex flex-col gap-0.5">
                  <dt className="text-[11px] text-ink-muted">التشغيل</dt>
                  <dd className="font-semibold">{selected.operation ?? "—"}</dd>
                </div>
                <div className="flex flex-col gap-0.5">
                  <dt className="text-[11px] text-ink-muted">آخر تحديث للموقع</dt>
                  <dd className="font-semibold">
                    {sinceText(selected.live?.last_received_at ?? null, now)}
                  </dd>
                </div>
                <div className="flex flex-col gap-0.5">
                  <dt className="text-[11px] text-ink-muted">السرعة</dt>
                  <dd className="font-semibold">
                    {selected.live?.speed_kmh != null ? (
                      <span className="ltr-nums">{Math.round(selected.live.speed_kmh)} كم/س</span>
                    ) : (
                      "—"
                    )}
                  </dd>
                </div>
              </dl>
              {selected.live ? (
                <Link
                  href={`/shifts/${selected.live.shift_id}`}
                  className="flex h-10 items-center justify-center rounded-[10px] bg-primary text-[13px] font-semibold text-white hover:bg-primary-hover"
                >
                  عرض المسار
                </Link>
              ) : (
                <Link
                  href={`/vehicles/${selected.id}`}
                  className="flex h-10 items-center justify-center rounded-[10px] border border-line-strong text-[13px] font-semibold text-primary hover:bg-neutral-50"
                >
                  بيانات السيارة
                </Link>
              )}
            </div>
          ) : null}
          {error ? (
            <p
              role="status"
              className="absolute top-3 right-3 z-[500] rounded-[10px] bg-danger-soft px-3 py-1.5 text-xs font-semibold text-danger"
            >
              تعذر تحديث المواقع، سيتم إعادة المحاولة
            </p>
          ) : null}
        </div>

        <ul
          aria-label="السيارات"
          className="flex max-h-[460px] min-w-0 flex-[1_1_250px] flex-col overflow-y-auto border-line max-[700px]:border-t min-[701px]:border-r"
        >
          {list.length === 0 ? (
            <li className="px-4 py-6 text-sm text-ink-muted">لا توجد سيارات نشطة.</li>
          ) : null}
          {list.map((r) => {
            const on = r.id === selected?.id;
            return (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(r.id)}
                  aria-pressed={on}
                  className={clsx(
                    "flex w-full items-center gap-3 border-b border-neutral-100 px-4 py-3 text-start",
                    on
                      ? "bg-[#f1f6ec] shadow-[inset_-3px_0_0_var(--color-lime-400)]"
                      : "bg-surface hover:bg-neutral-50",
                  )}
                >
                  <Dot status={r.status} />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-sm font-semibold text-ink">{r.plate}</span>
                    <span className="truncate text-xs text-ink-muted">
                      {r.driver ?? "بدون سائق"} · {r.operation ?? FLEET_STATUS[r.status].label}
                    </span>
                  </span>
                  <span className="text-[11px] whitespace-nowrap text-ink-muted">
                    {r.live ? sinceText(r.live.last_received_at, now) : "—"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
