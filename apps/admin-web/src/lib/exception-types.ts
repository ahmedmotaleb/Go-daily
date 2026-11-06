import type { Ref } from "@/lib/finance-types";

export type ExceptionStatus =
  "OPEN" | "UNDER_REVIEW" | "EXPLAINED" | "CORRECTED" | "DISMISSED" | "ESCALATED";
export type ExceptionSeverity = "LOW" | "MEDIUM" | "HIGH";
export type ExceptionLabel = "REVIEW_REQUIRED" | "UNUSUAL";

export type OperationalException = {
  id: string;
  rule_code: string;
  rule_title: string;
  severity: ExceptionSeverity;
  label: ExceptionLabel;
  summary: string;
  evidence: Record<string, unknown>;
  occurred_at: string;
  occurred_until: string | null;
  detected_at: string;
  last_detected_at: string;
  cleared_at: string | null;
  vehicle: Ref | null;
  driver: Ref | null;
  shift_id: string | null;
  subject_type: string | null;
  subject_id: string | null;
  status: ExceptionStatus;
  reviewer: { id: string; full_name: string } | null;
  reviewed_at: string | null;
  review_notes: string | null;
  resolution: string | null;
  allowed_transitions: ExceptionStatus[];
  updated_at: string;
};

export type ExceptionRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  window_start: string;
  window_end: string;
  trigger: string;
  results: Record<string, { found?: number; new?: number; skipped?: string }>;
  errors: Record<string, string>;
};

export type ExceptionRules = {
  rules: {
    code: string;
    title_ar: string;
    description_ar: string;
    label: ExceptionLabel;
    enabled: boolean;
  }[];
  thresholds: Record<string, unknown>;
  last_run: ExceptionRun | null;
};

export type ExceptionSummary = {
  active: number;
  by_status: Record<string, number>;
  by_severity: Record<ExceptionSeverity, number>;
  by_rule: Record<string, number>;
};
