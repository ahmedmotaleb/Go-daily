/** Close-outs, cash collections and day-offs (API: /cash/*, /day-offs). Money is decimal strings. */

export type PersonRef = { id: string; full_name: string };
export type VehicleRef = { id: string; internal_code: string; plate_number: string };

export type CloseoutStatus = "WAITING" | "PARTIAL" | "COLLECTED" | "NOTHING_DUE";

export type CloseoutLine = {
  key: "gas" | "gasoline" | "toll" | "maintenance";
  label: string;
  quantity: string | null;
  unit: string | null;
  amount: string;
  record_status: "SUBMITTED" | "APPROVED" | "REJECTED" | "VOIDED" | null;
  deducted: boolean;
};

export type CashCollection = {
  id: string;
  driver_id: string;
  closeout_id: string | null;
  amount: string;
  collected_at: string;
  note: string | null;
  collected_by: PersonRef | null;
  voided_at: string | null;
  void_reason: string | null;
};

export type Closeout = {
  id: string;
  shift_id: string;
  driver: PersonRef;
  vehicle: VehicleRef;
  service_date: string;
  submitted_at: string;
  source: "ADMIN" | "DRIVER_APP" | "SYSTEM";
  operation_label: string;
  start_odometer_km: number | null;
  end_odometer_km: number;
  start_odometer_photo_id: string | null;
  collection_amount: string;
  collection_booked: boolean;
  lines: CloseoutLine[];
  maintenance_kind: "NONE" | "OIL_CHANGE" | "MAINTENANCE";
  maintenance_note: string | null;
  notes: string | null;
  receipt_attachment_ids: string[];
  deductions: string;
  net_amount: string;
  carried_before: string;
  total_due: string;
  collected: string;
  remaining: string;
  status: CloseoutStatus;
  collections: CashCollection[];
  voided_at: string | null;
  void_reason: string | null;
};

export type DayOff = {
  id: string;
  driver: PersonRef;
  day: string;
  note: string | null;
  source: "ADMIN" | "DRIVER_APP" | "SYSTEM";
  created_at: string;
};

export type BoardRow = {
  kind: "CLOSEOUT" | "DAY_OFF" | "OPEN_SHIFT" | "ENDED_NOT_CLOSED";
  driver: PersonRef;
  vehicle: VehicleRef | null;
  operation_label: string | null;
  closeout: Closeout | null;
  day_off: DayOff | null;
  shift_id: string | null;
  started_at: string | null;
  outstanding: string;
};

export type CashBoard = {
  day: string;
  net_due: string;
  closeouts: number;
  collected: string;
  open_balance: string;
  day_offs: number;
  open_shifts: number;
  rows: BoardRow[];
};
