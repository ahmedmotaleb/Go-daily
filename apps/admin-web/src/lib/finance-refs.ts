import "server-only";
import { api } from "./api";
import type { Driver, Page, Vehicle } from "./types";

export type Option = { value: string; label: string };

/** Vehicle and driver choices for finance forms and filters. */
export async function fleetOptions(): Promise<{ vehicles: Option[]; drivers: Option[] }> {
  const [vehicles, drivers] = await Promise.all([
    api.get<Page<Vehicle>>("/vehicles", { page_size: 100, sort: "code" }),
    api.get<Page<Driver>>("/drivers", { page_size: 100 }),
  ]);
  return {
    vehicles: vehicles.items.map((v) => ({
      value: v.id,
      label: `${v.internal_code} · ${v.plate_number}${v.is_active ? "" : " (موقوفة)"}`,
    })),
    drivers: drivers.items.map((d) => ({ value: d.id, label: d.full_name })),
  };
}
