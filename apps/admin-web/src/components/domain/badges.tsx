import { EMPLOYMENT_STATUS_LABELS_AR, EXPIRY_STATUS_LABELS_AR } from "@go-daily/shared";
import { Badge, type Tone } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";
import type { Driver, ExpiryStatus } from "@/lib/types";

const EXPIRY_TONES: Record<ExpiryStatus, Tone> = {
  OK: "success",
  EXPIRING_SOON: "warning",
  EXPIRED: "danger",
  UNKNOWN: "neutral",
};

export function ExpiryBadge({ status, date }: { status: ExpiryStatus; date: string | null }) {
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <Badge tone={EXPIRY_TONES[status]}>{EXPIRY_STATUS_LABELS_AR[status]}</Badge>
      {date ? <span className="ltr-nums text-xs text-ink-muted">{formatDate(date)}</span> : null}
    </span>
  );
}

export function ActiveBadge({ active }: { active: boolean }) {
  return active ? <Badge tone="success">نشطة</Badge> : <Badge>موقوفة</Badge>;
}

const EMPLOYMENT_TONES: Record<Driver["employment_status"], Tone> = {
  ACTIVE: "success",
  ON_LEAVE: "info",
  SUSPENDED: "warning",
  TERMINATED: "neutral",
};

export function EmploymentBadge({ status }: { status: Driver["employment_status"] }) {
  return <Badge tone={EMPLOYMENT_TONES[status]}>{EMPLOYMENT_STATUS_LABELS_AR[status]}</Badge>;
}
