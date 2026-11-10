import type { Tone } from "@/components/ui/badge";
import type { TrackingState } from "@/lib/types";

/** Vehicle status as the design shows it, derived from the live tracking state. */
export type FleetStatus = "active" | "stale" | "critical" | "inactive";

export function fleetStatus(state: TrackingState | null): FleetStatus {
  switch (state) {
    case "ONLINE":
      return "active";
    case "STALE":
      return "stale";
    case "OFFLINE":
      return "critical"; // in a shift but no recent position
    default:
      return "inactive";
  }
}

export const FLEET_STATUS: Record<FleetStatus, { label: string; tone: Tone; dot: string }> = {
  active: {
    label: "نشطة · يتم التتبع",
    tone: "success",
    dot: "bg-forest-800 shadow-[0_0_0_3px_var(--color-lime-400)]",
  },
  stale: {
    label: "الموقع لم يتحدث",
    tone: "warning",
    dot: "bg-amber-400 shadow-[0_0_0_3px_#fbe7c4]",
  },
  critical: {
    label: "انقطاع GPS",
    tone: "danger",
    dot: "bg-red-400 shadow-[0_0_0_3px_#f6d3d2]",
  },
  inactive: {
    label: "غير نشطة",
    tone: "neutral",
    dot: "bg-neutral-400 shadow-[0_0_0_3px_var(--color-neutral-200)]",
  },
};

/** "منذ 12 ث" / "منذ 9 د" / "منذ 2 س" / "منذ 3 يوم" from an ISO instant. */
export function sinceText(iso: string | null, now: number = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `منذ ${seconds} ث`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `منذ ${minutes} د`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `منذ ${hours} س`;
  return `منذ ${Math.round(hours / 24)} يوم`;
}
