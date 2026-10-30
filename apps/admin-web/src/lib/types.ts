import type { Role } from "@go-daily/shared";

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type User = {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CurrentUser = User & { permissions: string[] };

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: CurrentUser;
};

export type ExpiryStatus = "OK" | "EXPIRING_SOON" | "EXPIRED" | "UNKNOWN";

export type VehicleType = {
  id: string;
  code: string;
  name_ar: string;
  name_en: string | null;
  is_active: boolean;
  sort_order: number;
};

export type AssignmentSummary = {
  id: string;
  driver_id: string;
  driver_name: string;
  vehicle_id: string;
  vehicle_code: string;
  vehicle_plate: string;
  role: "PRIMARY" | "RELIEF";
  starts_at: string;
};

export type Vehicle = {
  id: string;
  internal_code: string;
  plate_number: string;
  vehicle_type: VehicleType;
  manufacturer: string | null;
  model: string | null;
  model_year: number | null;
  color: string | null;
  ownership_status: "OWNED" | "LEASED" | "PARTNER" | "DRIVER_OWNED" | "OTHER";
  is_active: boolean;
  current_odometer_km: number | null;
  license_expiry: string | null;
  insurance_expiry: string | null;
  license_status: ExpiryStatus;
  insurance_status: ExpiryStatus;
  notes: string | null;
  current_assignments: AssignmentSummary[];
  created_at: string;
  updated_at: string;
};

export type Driver = {
  id: string;
  full_name: string;
  phone: string;
  national_id_masked: string | null;
  license_number: string | null;
  license_expiry: string | null;
  license_status: ExpiryStatus;
  employment_status: "ACTIVE" | "ON_LEAVE" | "SUSPENDED" | "TERMINATED";
  hire_date: string | null;
  end_date: string | null;
  notes: string | null;
  user_id: string | null;
  app_account_active: boolean | null;
  current_assignments: AssignmentSummary[];
  created_at: string;
  updated_at: string;
};

export type Assignment = {
  id: string;
  driver_id: string;
  driver_name: string;
  vehicle_id: string;
  vehicle_code: string;
  vehicle_plate: string;
  role: "PRIMARY" | "RELIEF";
  starts_at: string;
  ends_at: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
};

export type CompensationPlan = {
  id: string;
  driver_id: string;
  method: "FIXED_MONTHLY" | "DAILY_WAGE" | "REVENUE_PERCENTAGE" | "FIXED_PLUS_INCENTIVE";
  fixed_monthly_amount: string | null;
  daily_wage_amount: string | null;
  revenue_percentage: string | null;
  incentive_percentage: string | null;
  incentive_threshold_amount: string | null;
  effective_from: string;
  effective_to: string | null;
  notes: string | null;
  created_at: string;
};

export type OperationKind =
  "RIDE_HAILING" | "FIXED_ROUTE" | "SCHOOL_ROUTE" | "PRIVATE_TRIP" | "EMPLOYEE_TRANSPORT" | "OTHER";

export type OperationType = {
  id: string;
  code: string;
  kind: OperationKind;
  name_ar: string;
  name_en: string | null;
  is_active: boolean;
  sort_order: number;
  uses_routes: boolean;
};

export type RouteStop = {
  id: string;
  sequence: number;
  kind: "ORIGIN" | "INTERMEDIATE" | "DESTINATION";
  name: string;
  latitude: string | null;
  longitude: string | null;
  radius_m: number;
};

export type Route = {
  id: string;
  name: string;
  operation_type: OperationType;
  trip_pattern: "ONE_WAY" | "ROUND_TRIP";
  is_active: boolean;
  expected_distance_km: string | null;
  expected_duration_minutes: number | null;
  window_start: string | null;
  window_end: string | null;
  operating_days: number[] | null;
  notes: string | null;
  stops: RouteStop[];
  created_at: string;
  updated_at: string;
};

export type OperationTypeRef = { id: string; code: string; kind: OperationKind; name_ar: string };

export type OperationSession = {
  id: string;
  shift_id: string;
  operation_type: OperationTypeRef;
  route: { id: string; name: string } | null;
  status: "ACTIVE" | "COMPLETED" | "CANCELLED";
  started_at: string;
  ended_at: string | null;
  start_odometer_km: number | null;
  end_odometer_km: number | null;
  notes: string | null;
};

export type ShiftStatus = "PLANNED" | "ACTIVE" | "COMPLETED" | "CANCELLED";

export type Shift = {
  id: string;
  driver: { id: string; full_name: string };
  vehicle: { id: string; internal_code: string; plate_number: string };
  status: ShiftStatus;
  source: "ADMIN" | "DRIVER_APP";
  planned_start_at: string | null;
  planned_end_at: string | null;
  planned_operation_type: OperationTypeRef | null;
  planned_route: { id: string; name: string } | null;
  started_at: string | null;
  ended_at: string | null;
  start_odometer_km: number | null;
  end_odometer_km: number | null;
  odometer_distance_km: number | null;
  duration_minutes: number | null;
  assignment_override_reason: string | null;
  cancel_reason: string | null;
  notes: string | null;
  sessions: OperationSession[];
  active_session: OperationSession | null;
  created_at: string;
  updated_at: string;
};

export type DashboardSummary = {
  generated_at: string;
  kpis: {
    active_vehicles: number;
    active_drivers: number;
    active_shifts: number;
    today_shifts: number;
  };
  active_shifts: Shift[];
  vehicles: {
    id: string;
    internal_code: string;
    plate_number: string;
    vehicle_type: string;
    driver_name: string | null;
    in_shift: boolean;
    current_operation: string | null;
  }[];
  assignments: AssignmentSummary[];
  expiring_documents: {
    kind: "VEHICLE_LICENSE" | "VEHICLE_INSURANCE" | "DRIVER_LICENSE";
    entity_type: "vehicle" | "driver";
    entity_id: string;
    label: string;
    expires_on: string;
    status: ExpiryStatus;
  }[];
  recent_activity: {
    id: string;
    occurred_at: string;
    action: string;
    entity_type: string | null;
    entity_id: string | null;
    actor_name: string | null;
  }[];
};
