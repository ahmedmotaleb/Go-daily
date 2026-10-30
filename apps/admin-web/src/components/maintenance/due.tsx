import Link from "next/link";
import { Badge, type Tone } from "@/components/ui/badge";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { formatDate, formatNumber } from "@/lib/format";
import type { DueItem, DueState } from "@/lib/maintenance-types";

const STATE: Record<DueState, { label: string; tone: Tone }> = {
  OVERDUE: { label: "متأخرة", tone: "danger" },
  DUE_SOON: { label: "قريبة", tone: "warning" },
  OK: { label: "في موعدها", tone: "success" },
  UNKNOWN: { label: "بدون نقطة بداية", tone: "neutral" },
};

export function DueBadge({ state }: { state: DueState }) {
  return <Badge tone={STATE[state].tone}>{STATE[state].label}</Badge>;
}

function remaining(row: DueItem) {
  const parts: string[] = [];
  if (row.km_left !== null) {
    parts.push(
      row.km_left < 0
        ? `متجاوزة ${formatNumber(-row.km_left)} كم`
        : `${formatNumber(row.km_left)} كم`,
    );
  }
  if (row.days_left !== null) {
    parts.push(
      row.days_left < 0
        ? `متأخرة ${formatNumber(-row.days_left)} يوم`
        : `${formatNumber(row.days_left)} يوم`,
    );
  }
  return parts.join(" · ") || "—";
}

export function DueTable({ rows, showVehicle = true }: { rows: DueItem[]; showVehicle?: boolean }) {
  return (
    <Table>
      <THead>
        <tr>
          {showVehicle ? <TH>المركبة</TH> : null}
          <TH>الصيانة</TH>
          <TH>آخر تنفيذ</TH>
          <TH>الاستحقاق التالي</TH>
          <TH>المتبقي</TH>
          <TH>الحالة</TH>
        </tr>
      </THead>
      <tbody>
        {rows.map((row) => (
          <TR key={row.schedule_id} className={row.is_active ? undefined : "opacity-60"}>
            {showVehicle ? (
              <TD>
                <Link
                  href={`/vehicles/${row.vehicle.id}`}
                  className="ltr-nums font-semibold text-forest-700 hover:underline"
                >
                  {row.vehicle.name}
                </Link>
              </TD>
            ) : null}
            <TD>
              {row.type.name_ar}
              <span className="block text-xs text-ink-muted">
                كل {row.interval_km ? `${formatNumber(row.interval_km)} كم` : ""}
                {row.interval_km && row.interval_days ? " أو " : ""}
                {row.interval_days ? `${formatNumber(row.interval_days)} يوم` : ""}
              </span>
            </TD>
            <TD>
              {row.last_performed_on ? formatDate(row.last_performed_on) : "—"}
              {row.last_odometer_km !== null ? (
                <span className="ltr-nums block text-xs text-ink-muted">
                  {formatNumber(row.last_odometer_km)} كم
                </span>
              ) : null}
            </TD>
            <TD>
              {row.next_due_date ? formatDate(row.next_due_date) : ""}
              {row.next_due_km !== null ? (
                <span className="ltr-nums block text-xs text-ink-muted">
                  {formatNumber(row.next_due_km)} كم
                </span>
              ) : null}
            </TD>
            <TD className="ltr-nums">{remaining(row)}</TD>
            <TD>
              <DueBadge state={row.state} />
              {row.is_active ? null : <Badge className="ms-1">موقوف</Badge>}
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
