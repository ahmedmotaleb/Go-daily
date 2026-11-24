import type { Metadata } from "next";
import type { LatLng } from "@/components/map/types";
import { DateJump } from "@/components/tracking/date-jump";
import {
  TrackingCenter,
  type ListRow,
  type SelectedShift,
} from "@/components/tracking/tracking-center";
import { BarToggle, WorkspaceBar } from "@/components/tracking/workspace-bar";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetStatus, type FleetStatus } from "@/lib/fleet-status";
import { tileConfig } from "@/lib/map-config";
import { cairoToday, spDate, spEnum, spUuid } from "@/lib/search";
import type { DashboardSummary, LivePosition, Page, Route, Shift, ShiftTrack } from "@/lib/types";

export const metadata: Metadata = { title: "مركز التتبع المباشر" };

const ORDER: Record<FleetStatus, number> = { critical: 0, stale: 1, active: 2, inactive: 3 };

function operationOf(shift: Shift): string {
  const session = shift.active_session ?? shift.sessions[shift.sessions.length - 1] ?? null;
  const type = session?.operation_type ?? shift.planned_operation_type;
  return type?.name_ar ?? "بدون تشغيل محدد";
}

/** Straight lines between the route's stops: an approximation, labelled as such on the map. */
async function expectedPath(shift: Shift): Promise<LatLng[]> {
  const session = shift.active_session ?? shift.sessions[shift.sessions.length - 1] ?? null;
  const routeId = session?.route?.id ?? shift.planned_route?.id;
  if (!routeId) return [];
  try {
    const route = await api.get<Route>(`/routes/${routeId}`);
    return [...route.stops]
      .sort((a, b) => a.sequence - b.sequence)
      .filter((s) => s.latitude !== null && s.longitude !== null)
      .map((s) => ({ lat: Number(s.latitude), lng: Number(s.longitude) }));
  } catch {
    return [];
  }
}

async function loadShift(id: string, withRoute: boolean): Promise<SelectedShift | null> {
  try {
    const [shift, track] = await Promise.all([
      api.get<Shift>(`/shifts/${id}`),
      api.get<ShiftTrack>(`/shifts/${id}/track`),
    ]);
    return { shift, track, expected: withRoute ? await expectedPath(shift) : [] };
  } catch {
    return null;
  }
}

export default async function TrackingPage({ searchParams }: PageProps<"/tracking">) {
  const user = await requirePermission("tracking:read");
  const sp = await searchParams;
  const mode = spEnum(sp, "mode", ["live", "replay"] as const) ?? "live";
  const today = cairoToday();
  const date = spDate(sp, "date") ?? today;
  const canShifts = can(user, "shifts:read");
  const canRoutes = can(user, "operations:read");

  const live = await api.get<LivePosition[]>("/tracking/live");
  let rows: ListRow[] = [];
  let shiftId = spUuid(sp, "shift");

  if (mode === "live") {
    const summary = await api.get<DashboardSummary>("/dashboard/summary");
    const byVehicle = new Map(live.map((p) => [p.vehicle_id, p]));
    shiftId ??= (live.find((p) => p.state === "ONLINE") ?? live[0])?.shift_id;
    rows = summary.vehicles
      .map((v) => {
        const p = byVehicle.get(v.id) ?? null;
        return {
          key: v.id,
          vehicleId: v.id,
          href: p && canShifts ? `/tracking?shift=${p.shift_id}` : null,
          plate: v.plate_number,
          driver: p?.driver_name ?? v.driver_name ?? "بدون سائق",
          operation: p?.current_operation ?? v.current_operation ?? "بدون تشغيل",
          status: fleetStatus(p ? p.state : null),
          lastReceived: p?.last_received_at ?? null,
          selected: !!p && p.shift_id === shiftId,
        };
      })
      .sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.plate.localeCompare(b.plate));
  } else if (canShifts) {
    const shifts = await api.get<Page<Shift>>("/shifts", { day: date, page_size: 100 });
    const started = shifts.items.filter((s) => s.started_at && s.status !== "CANCELLED");
    shiftId ??= started[0]?.id;
    rows = started.map((s) => ({
      key: s.id,
      vehicleId: s.vehicle.id,
      href: `/tracking?mode=replay&date=${date}&shift=${s.id}`,
      plate: s.vehicle.plate_number,
      driver: s.driver.full_name,
      operation: operationOf(s),
      status: s.status === "ACTIVE" ? "active" : "inactive",
      lastReceived: null,
      selected: s.id === shiftId,
    }));
  }

  const selected = shiftId && canShifts ? await loadShift(shiftId, canRoutes) : null;

  return (
    <>
      <WorkspaceBar title="مركز التتبع المباشر وإعادة المسار">
        <BarToggle
          label="وضع العرض"
          options={[
            { href: "/tracking", label: "مباشر", active: mode === "live" },
            {
              href: `/tracking?mode=replay&date=${date}`,
              label: "إعادة المسار",
              active: mode === "replay",
            },
          ]}
        />
        {mode === "replay" ? (
          <DateJump value={date} basePath="/tracking" extra={{ mode: "replay" }} />
        ) : null}
      </WorkspaceBar>
      <main id="main" className="flex flex-1 flex-col">
        <TrackingCenter
          key={`${mode}-${date}`}
          mode={mode}
          rows={rows}
          selected={selected}
          live={live}
          tiles={tileConfig()}
        />
      </main>
    </>
  );
}
