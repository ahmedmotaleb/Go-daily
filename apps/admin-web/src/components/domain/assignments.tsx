import { ASSIGNMENT_ROLE_LABELS_AR, options } from "@go-daily/shared";
import Link from "next/link";
import { endAssignmentAction, createAssignmentAction } from "@/app/(app)/assignments/actions";
import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, FieldError, SelectField, TextField } from "@/components/forms/fields";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import type { Assignment, AssignmentSummary } from "@/lib/types";

type Side = "vehicle" | "driver";

export function CurrentAssignments({
  side,
  assignments,
  canWrite,
}: {
  side: Side;
  assignments: AssignmentSummary[];
  canWrite: boolean;
}) {
  if (assignments.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        {side === "vehicle"
          ? "لا يوجد سائق مكلف بهذه المركبة حاليًا."
          : "السائق غير مكلف بأي مركبة حاليًا."}
      </p>
    );
  }
  return (
    <ul className="space-y-4">
      {assignments.map((a) => (
        <li key={a.id} className="rounded-[var(--radius-control)] border border-line p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              {side === "vehicle" ? (
                <Link
                  href={`/drivers/${a.driver_id}`}
                  className="font-semibold text-forest-700 hover:underline"
                >
                  {a.driver_name}
                </Link>
              ) : (
                <Link
                  href={`/vehicles/${a.vehicle_id}`}
                  className="font-semibold text-forest-700 hover:underline"
                >
                  <span className="ltr-nums">{a.vehicle_code}</span> · {a.vehicle_plate}
                </Link>
              )}
              <p className="text-xs text-ink-muted">منذ {formatDateTime(a.starts_at)}</p>
            </div>
            <Badge tone={a.role === "PRIMARY" ? "active" : "info"}>
              {ASSIGNMENT_ROLE_LABELS_AR[a.role]}
            </Badge>
          </div>
          {canWrite ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm font-medium text-ink-muted hover:text-ink">
                إنهاء التكليف
              </summary>
              <div className="mt-3">
                <ActionForm
                  action={endAssignmentAction.bind(null, a.id, a.driver_id, a.vehicle_id)}
                  submitLabel="إنهاء التكليف"
                  variant="secondary"
                  confirm="إنهاء هذا التكليف؟ سيبقى محفوظًا في السجل."
                >
                  <input
                    type="hidden"
                    name="return_to"
                    value={
                      side === "vehicle" ? `/vehicles/${a.vehicle_id}` : `/drivers/${a.driver_id}`
                    }
                  />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <TextField
                      name="ends_at"
                      label="وقت النهاية"
                      type="datetime-local"
                      hint="اتركه فارغًا للآن"
                    />
                    <TextField name="notes" label="ملاحظة" />
                  </div>
                </ActionForm>
              </div>
            </details>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function AssignForm({
  side,
  fixedId,
  choices,
  hasCurrentPrimary,
}: {
  side: Side;
  fixedId: string;
  choices: { value: string; label: string }[];
  hasCurrentPrimary: boolean;
}) {
  const fixedName = side === "vehicle" ? "vehicle_id" : "driver_id";
  const choiceName = side === "vehicle" ? "driver_id" : "vehicle_id";
  return (
    <ActionForm action={createAssignmentAction} submitLabel="تسجيل التكليف" variant="accent">
      <input type="hidden" name={fixedName} value={fixedId} />
      <input
        type="hidden"
        name="return_to"
        value={`/${side === "vehicle" ? "vehicles" : "drivers"}/${fixedId}`}
      />
      <FieldError name={fixedName} />
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          name={choiceName}
          label={side === "vehicle" ? "السائق" : "المركبة"}
          options={choices}
          placeholder={side === "vehicle" ? "اختر السائق" : "اختر المركبة"}
          required
        />
        <SelectField
          name="role"
          label="نوع التكليف"
          defaultValue="PRIMARY"
          options={options(ASSIGNMENT_ROLE_LABELS_AR)}
        />
        <TextField
          name="starts_at"
          label="يبدأ من"
          type="datetime-local"
          hint="اتركه فارغًا للبدء الآن"
        />
        <TextField name="notes" label="ملاحظات" />
      </div>
      {hasCurrentPrimary ? (
        <CheckboxField
          name="replace_current"
          label="إنهاء التكليف الأساسي الحالي تلقائيًا عند بدء هذا التكليف"
        />
      ) : null}
    </ActionForm>
  );
}

export function AssignmentHistory({
  side,
  items,
  total,
}: {
  side: Side;
  items: Assignment[];
  total: number;
}) {
  return (
    <Card>
      <CardHeader
        title="سجل التكليفات"
        description={`إجمالي ${total} تكليف — لا يتم حذف أي تكليف سابق`}
      />
      {items.length === 0 ? (
        <EmptyState title="لا توجد تكليفات مسجلة" />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>{side === "vehicle" ? "السائق" : "المركبة"}</TH>
              <TH>النوع</TH>
              <TH>من</TH>
              <TH>إلى</TH>
              <TH>ملاحظات</TH>
            </tr>
          </THead>
          <tbody>
            {items.map((a) => (
              <TR key={a.id}>
                <TD className="font-medium">
                  {side === "vehicle" ? (
                    <Link href={`/drivers/${a.driver_id}`} className="hover:underline">
                      {a.driver_name}
                    </Link>
                  ) : (
                    <Link href={`/vehicles/${a.vehicle_id}`} className="hover:underline">
                      <span className="ltr-nums">{a.vehicle_code}</span> · {a.vehicle_plate}
                    </Link>
                  )}
                </TD>
                <TD>{ASSIGNMENT_ROLE_LABELS_AR[a.role]}</TD>
                <TD className="text-ink-muted">{formatDateTime(a.starts_at)}</TD>
                <TD>
                  {a.ends_at ? (
                    <span className="text-ink-muted">{formatDateTime(a.ends_at)}</span>
                  ) : (
                    <Badge tone="active">حالي</Badge>
                  )}
                </TD>
                <TD className="max-w-64 text-xs whitespace-pre-line text-ink-muted">
                  {a.notes ?? "—"}
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

export function AssignmentPanel({
  side,
  fixedId,
  current,
  choices,
  canWrite,
  canAssign,
  inactiveReason,
}: {
  side: Side;
  fixedId: string;
  current: AssignmentSummary[];
  choices: { value: string; label: string }[];
  canWrite: boolean;
  canAssign: boolean;
  inactiveReason?: string;
}) {
  return (
    <Card>
      <CardHeader title={side === "vehicle" ? "السائق المكلف" : "المركبة المكلف بها"} />
      <CardBody className="space-y-5">
        <CurrentAssignments side={side} assignments={current} canWrite={canWrite} />
        {canWrite ? (
          canAssign ? (
            <details open={current.length === 0}>
              <summary className="cursor-pointer text-sm font-semibold text-forest-700">
                {side === "vehicle" ? "تكليف سائق" : "تكليف بمركبة"}
              </summary>
              <div className="mt-3">
                <AssignForm
                  side={side}
                  fixedId={fixedId}
                  choices={choices}
                  hasCurrentPrimary={current.some((a) => a.role === "PRIMARY")}
                />
              </div>
            </details>
          ) : (
            <p className="text-sm text-ink-muted">{inactiveReason}</p>
          )
        ) : null}
      </CardBody>
    </Card>
  );
}
