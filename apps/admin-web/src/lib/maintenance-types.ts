import type { Ref, Reviewable } from "./finance-types";

export type MaintenanceType = {
  id: string;
  code: string;
  name_ar: string;
  interval_km: number | null;
  interval_days: number | null;
  is_active: boolean;
  sort_order: number;
  consumable_type_id?: string | null;
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
  consumable_quantity?: string | null;
  consumable_spec?: string | null;
  next_due_km?: number | null;
  next_due_on?: string | null;
};

export type OilReconciliation = {
  date_from: string;
  date_to: string;
  purchases: {
    id: string;
    vehicle: string;
    vehicle_id: string;
    day: string;
    item: string;
    quantity: string;
    unit: string;
    total_amount: string;
    used: string | null;
    services: string[];
    status: "NOT_LINKED" | "OVER_USED" | "PARTLY_USED" | "USED";
    label: string;
  }[];
  services: {
    id: string;
    vehicle: string;
    vehicle_id: string;
    day: string;
    service: string;
    quantity: string | null;
    spec: string | null;
    purchase_id: string | null;
    parts_cost: string;
    next_due_km: number | null;
    next_due_on: string | null;
    status: "NO_QUANTITY" | "NO_PURCHASE" | "OK";
    label: string;
  }[];
  expenses: {
    id: string;
    vehicle: string;
    vehicle_id: string;
    day: string;
    amount: string;
    service_id: string | null;
    status: "NO_SERVICE" | "MATCHED";
    label: string;
  }[];
  to_check: number;
};
