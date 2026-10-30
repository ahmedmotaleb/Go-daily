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
