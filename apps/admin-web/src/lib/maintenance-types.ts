import type { Ref, Reviewable } from "./finance-types";

export type MaintenanceType = {
  id: string;
  code: string;
  name_ar: string;
  interval_km: number | null;
  interval_days: number | null;
  is_active: boolean;
  sort_order: number;
};

export type DueState = "OK" | "DUE_SOON" | "OVERDUE" | "UNKNOWN";

export type DueItem = {
  schedule_id: string;
  vehicle: Ref;
  type: MaintenanceType;
  interval_km: number | null;
  interval_days: number | null;
  last_performed_on: string | null;
  last_odometer_km: number | null;
  current_odometer_km: number | null;
  next_due_km: number | null;
  next_due_date: string | null;
  km_left: number | null;
  days_left: number | null;
  state: DueState;
  is_active: boolean;
};

export type MaintenanceRecord = Reviewable & {
  vehicle: Ref;
  type: MaintenanceType;
  performed_on: string;
  odometer_km: number | null;
  vendor: string | null;
  parts_cost: string;
  labor_cost: string;
  other_cost: string;
  total_cost: string;
  description: string | null;
  downtime_start: string | null;
  downtime_end: string | null;
  downtime_hours: number | null;
  fuel_transaction_id: string | null;
};
