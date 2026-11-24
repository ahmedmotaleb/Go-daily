import { SESSION_STATUS_LABELS_AR, SHIFT_STATUS_LABELS_AR } from "@go-daily/shared";
import { Badge, type Tone } from "@/components/ui/badge";
import type { OperationSession, ShiftStatus } from "@/lib/types";

const SHIFT_TONES: Record<ShiftStatus, Tone> = {
  PLANNED: "info",
  ACTIVE: "active",
  COMPLETED: "success",
  CANCELLED: "neutral",
};

export function ShiftStatusBadge({ status }: { status: ShiftStatus }) {
  return <Badge tone={SHIFT_TONES[status]}>{SHIFT_STATUS_LABELS_AR[status]}</Badge>;
}

export function SessionStatusBadge({ status }: { status: OperationSession["status"] }) {
  const tone: Tone =
    status === "ACTIVE" ? "active" : status === "COMPLETED" ? "success" : "neutral";
  return <Badge tone={tone}>{SESSION_STATUS_LABELS_AR[status]}</Badge>;
}

export function formatDuration(minutes: number | null): string {
  if (minutes === null) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} س ${m} د` : `${m} د`;
}
