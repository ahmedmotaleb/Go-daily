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
  loops: number;
  legs: number;
  incomplete_legs: number;
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
  // First-entered readings, set when staff corrected them (null = never corrected).
  original_start_odometer_km: number | null;
  original_end_odometer_km: number | null;
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

export type TrackingState = "ONLINE" | "STALE" | "OFFLINE" | "NOT_IN_SHIFT";

export type LivePosition = {
  vehicle_id: string;
  vehicle_code: string;
  plate_number: string;
  driver_id: string;
  driver_name: string;
  shift_id: string;
  state: TrackingState;
  latitude: number | null;
  longitude: number | null;
  accuracy_m: number | null;
  speed_kmh: number | null;
  heading_deg: number | null;
  last_recorded_at: string | null;
  last_received_at: string | null;
  current_operation: string | null;
  last_event: string | null;
};

export type ShiftTrack = {
  shift_id: string;
  vehicle_id: string;
  driver_id: string;
  window_start: string | null;
  window_end: string | null;
  points: {
    t: string;
    lat: number;
    lng: number;
    acc: number | null;
    spd: number | null;
    q: string;
  }[];
  counts: Record<string, number>;
  gps_distance_km: number;
  odometer_distance_km: number | null;
  gaps: { start: string; end: string; seconds: number; displacement_m: number | null }[];
  stops: { start: string; end: string; seconds: number; latitude: number; longitude: number }[];
  timeline: { at: string; kind: string; label: string; until: string | null }[];
  quality: GpsQuality;
  odometer_reconciliation: OdometerReconciliation;
};

export type ReconciliationStatus =
  "WITHIN_TOLERANCE" | "REVIEW" | "MISSING_ODOMETER" | "INSUFFICIENT_GPS" | "NOT_COMPLETED";

export type OdometerReconciliation = {
  status: ReconciliationStatus;
  odometer_km: number | null;
  gps_km: number | null;
  difference_km: number | null;
  abs_difference_km: number | null;
  difference_pct: number | null;
  allowed_km: number | null;
  gps_coverage_pct: number | null;
  tolerance_pct: number;
  tolerance_km: number;
  min_gps_coverage_pct: number;
  missing: ("ODOMETER" | "GPS")[];
  odometer_corrected: boolean;
  original_start_odometer_km: number | null;
  original_end_odometer_km: number | null;
};

export type QualityGrade = "EXCELLENT" | "GOOD" | "NEEDS_REVIEW" | "INSUFFICIENT";

export type QualityCheck = {
  code:
    | "COVERAGE"
    | "LONGEST_GAP"
    | "MEDIAN_ACCURACY"
    | "LOW_ACCURACY_SHARE"
    | "IMPOSSIBLE_JUMPS"
    | "MOCK_POINTS"
    | "STALE_SHARE";
  value: number;
  unit: string;
  excellent: number;
  good: number;
  higher_is_better: boolean;
  grade: QualityGrade;
};

export type GpsQuality = {
  grade: QualityGrade;
  metrics: {
    duration_minutes: number;
    points: number;
    valid_points: number;
    low_accuracy_points: number;
    impossible_jumps: number;
    mock_points: number;
    coverage_pct: number | null;
    gaps: number;
    longest_gap_minutes: number;
    median_accuracy_m: number | null;
    stale_points: number;
    median_sync_delay_s: number | null;
    p95_sync_delay_s: number | null;
  };
  checks: QualityCheck[];
  insufficient_reason: "NOT_STARTED" | "TOO_SHORT" | "TOO_FEW_POINTS" | null;
  partial: boolean;
};

export type RouteEvent = {
  id: string;
  session_id: string;
  stop_id: string | null;
  stop_name: string | null;
  event_type:
    | "ENTERED"
    | "EXITED"
    | "REACHED_ORIGIN"
    | "REACHED_DESTINATION"
    | "LEG_COMPLETED"
    | "LOOP_COMPLETED"
    | "LEG_INCOMPLETE"
    | "LEG_REJECTED";
  direction: "OUTBOUND" | "INBOUND" | null;
  occurred_at: string;
  sequence_no: number | null;
  source: "AUTO" | "MANUAL";
  status: "ACTIVE" | "VOIDED";
  reason: string | null;
  void_reason: string | null;
  details: LegDetails | null;
};

/** Evidence the detector stores on leg events (U09). */
export type LegDetails = {
  started_at: string | null;
  seconds: number | null;
  from_stop_id: string | null;
  to_stop_id: string | null;
  visited_stop_ids: string[];
  in_route_order: boolean;
  reason?: "returned_to_start" | "session_ended" | "faster_than_minimum";
  min_seconds?: number;
};

export type SchoolRunStatus =
  | "SCHEDULED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "COMPLETED_LATE"
  | "INCOMPLETE"
  | "COMPLETED_UNVERIFIED"
  | "MISSED"
  | "CANCELLED";

export type SchoolRun = {
  id: string;
  route: { id: string; name: string };
  service_date: string;
  scheduled_start_at: string;
  scheduled_end_at: string;
  vehicle: { id: string; internal_code: string; plate_number: string };
  driver: { id: string; full_name: string } | null;
  status: SchoolRunStatus;
  session_id: string | null;
  shift_id: string | null;
  actual_start_at: string | null;
  actual_end_at: string | null;
  label: string | null;
  notes: string | null;
  status_reason: string | null;
  evidence: { reached_origin: boolean; reached_destination: boolean; route_events: number };
  verification: SchoolRunVerification | null;
};

/** What a school run's outcome rests on (U12). */
export type SchoolRunVerification = {
  required_stops: { id: string; name: string }[];
  reached_stops: string[];
  missing_stops: string[];
  arrived_at: string | null;
  start_delay_minutes: number | null;
  arrival_delay_minutes: number | null;
  late_grace_minutes: number;
  gps_points: number;
  gps_coverage_pct: number;
  min_gps_coverage_pct: number;
  max_deviation_m: number | null;
  corridor_m: number;
};

export type ExpectedRevenueModel = "PER_LOOP" | "PER_LEG" | "PASSENGERS_X_FARE";

/** Expected collection rate of a route, versioned by date (U10). */
export type RouteRevenueRate = {
  id: string;
  route_id: string;
  model: ExpectedRevenueModel;
  amount_per_loop: string | null;
  amount_per_leg: string | null;
  fare: string | null;
  passengers_per_leg: number | null;
  effective_from: string;
  effective_to: string | null;
  notes: string | null;
  created_at: string;
};

export type MoneySplit = { approved: string; pending: string; total: string };

/** GET /dashboard/today — money fields are null without finance permissions. */
export type TodayOverview = {
  generated_at: string;
  oldest_shift_started_at: string | null;
  revenue: MoneySplit | null;
  fuel: MoneySplit | null;
  other_expenses: MoneySplit | null;
  week: { day: string; revenue: string; expenses: string }[];
  operations: {
    kind: string;
    name_ar: string;
    vehicles: number;
    active_sessions: number;
    sessions_today: number;
    activity_label: string;
    activity_value: string;
    progress_pct: number | null;
    note: string | null;
    note_is_warning: boolean;
    collection: string | null;
  }[];
};

/** Operations control center row (U23). Money and cases are null without permission. */
export type ControlRow = {
  vehicle_id: string;
  vehicle_code: string;
  plate_number: string;
  driver_id: string;
  driver_name: string;
  shift_id: string;
  shift_started_at: string | null;
  operation: string | null;
  tracking_state: TrackingState;
  latitude: number | null;
  longitude: number | null;
  last_received_at: string | null;
  speed_kmh: number | null;
  loops: number;
  legs: number;
  school_done: number;
  school_planned: number;
  school_attention: number;
  collection_today: string | null;
  fuel_today: string | null;
  open_cases: number | null;
  case_titles: string[];
};

export type ControlCenter = { generated_at: string; rows: ControlRow[] };

/** Vehicle daily timeline item (U24). `at` is null for day-level records. */
export type TimelineItem = {
  at: string | null;
  kind: string;
  title: string;
  detail: string | null;
  amount: string | null;
  status: string | null;
  until: string | null;
  link: string | null;
};

/** Pilot command center and daily close (U50/U51). */
export type PilotCheckState = "OK" | "MISSING" | "REVIEW" | "NOT_APPLICABLE";
export type PilotVerdict = "COMPLETE" | "INCOMPLETE" | "NEEDS_REVIEW";

export type PilotShift = {
  shift_id: string;
  driver_name: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  operations: string[];
  gps_km: number;
  odometer_km: number | null;
  gps_grade: string;
  odometer_status: string;
  loops: number;
  legs: number;
};

export type PilotDay = {
  vehicle_id: string;
  vehicle_code: string;
  plate_number: string;
  day: string;
  drivers: string[];
  day_off: boolean;
  shifts: PilotShift[];
  tracking_state: string | null;
  last_received_at: string | null;
  fuel: string;
  expenses: string;
  revenue: string;
  closeout_net: string;
  collected: string;
  remaining: string;
  open_cases: { id: string; summary: string }[];
  checks: { code: string; label: string; state: PilotCheckState; detail: string }[];
  verdict: PilotVerdict;
  verdict_ar: string;
};
