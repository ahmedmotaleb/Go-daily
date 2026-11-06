export type ReportColumnType = "text" | "number" | "money" | "date" | "datetime" | "minutes" | "km";
export type ReportFilter =
  "vehicle" | "driver" | "operation_type" | "route" | "fuel_type" | "category" | "period";

export type ReportInfo = {
  code: string;
  title: string;
  description: string;
  filters: ReportFilter[];
};

export type ReportColumn = { key: string; label: string; type: ReportColumnType; total: boolean };

export type ReportTable = {
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, unknown>;
};

export type Report = ReportTable & {
  code: string;
  title: string;
  date_from: string;
  date_to: string;
  summaries: (ReportTable & { title: string })[];
  notes: string[];
};

/** Query keys the API accepts for report filters. */
export const FILTER_PARAM: Record<ReportFilter, string> = {
  vehicle: "vehicle_id",
  driver: "driver_id",
  operation_type: "operation_type_id",
  route: "route_id",
  fuel_type: "fuel_type_id",
  category: "category_id",
  period: "period",
};

/** Grouping choices for period-based reports (fuel efficiency). */
export const PERIODS = ["week", "month", "day", "shift"] as const;
export const PERIOD_LABELS: Record<(typeof PERIODS)[number], string> = {
  week: "أسبوع",
  month: "شهر",
  day: "يوم",
  shift: "وردية",
};

export const REPORT_CODE = /^[a-z_]{2,40}$/;
