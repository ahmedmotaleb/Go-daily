import { recordPassengerCountAction, voidPassengerCountAction } from "@/app/(app)/shifts/actions";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Shift } from "@/lib/types";

type Count = {
  id: string;
  session_id: string | null;
  direction: "OUTBOUND" | "INBOUND" | null;
  counted_at: string;
  passengers: number;
  source: "DRIVER" | "SUPERVISOR" | "TICKETING" | "HARDWARE";
  confidence: "COUNTED" | "ESTIMATED";
  note: string | null;
  voided_at: string | null;
  void_reason: string | null;
};

const SOURCE: Record<Count["source"], string> = {
  DRIVER: "بلاغ السائق",
  SUPERVISOR: "عد المشرف",
  TICKETING: "نظام التذاكر",
  HARDWARE: "جهاز العد",
};
const CONFIDENCE: Record<Count["confidence"], string> = { COUNTED: "عد فعلي", ESTIMATED: "تقديري" };
const DIRECTION = { OUTBOUND: "ذهاب", INBOUND: "عودة" } as const;

/** U11: recorded passenger counts, with where each came from. Never inferred from GPS. */
export async function PassengerCounts({ shift, canWrite }: { shift: Shift; canWrite: boolean }) {
  const counts = await api.get<Count[]>(`/shifts/${shift.id}/passenger-counts`);
  const live = counts.filter((c) => !c.voided_at);
  return (
    <Card>
      <CardHeader
        title="عدد الركاب"
        description="يُسجل من السائق أو المشرف مع مصدره؛ لا يُستنتج من GPS"
        actions={
          live.length ? (
            <span className="ltr-nums text-sm font-semibold">
              {formatNumber(live.reduce((n, c) => n + c.passengers, 0))} راكب
            </span>
          ) : null
        }
      />
      <CardBody className="space-y-4">
        {counts.length === 0 ? (
          <p className="text-sm text-ink-muted">لم يُسجل عد لهذه الوردية.</p>
        ) : (
          <ul className="divide-y divide-line text-sm">
            {counts.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  <span className="ltr-nums font-semibold">{formatNumber(c.passengers)}</span> راكب
                  {c.direction ? ` · ${DIRECTION[c.direction]}` : ""} ·{" "}
                  {formatDateTime(c.counted_at)}
                  <span className="ms-2 text-xs text-ink-muted">
                    {SOURCE[c.source]} · {CONFIDENCE[c.confidence]}
                    {c.note ? ` · ${c.note}` : ""}
                  </span>
                  {c.voided_at ? <Badge className="ms-2">ملغي: {c.void_reason}</Badge> : null}
                </span>
                {canWrite && !c.voided_at ? (
                  <details>
                    <summary className="cursor-pointer text-xs text-primary">إلغاء</summary>
                    <ActionForm
                      action={voidPassengerCountAction.bind(null, shift.id, c.id)}
                      submitLabel="إلغاء العد"
                      variant="danger"
                      className="mt-2"
                    >
                      <TextField name="reason" label="السبب" required />
                    </ActionForm>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canWrite && shift.started_at ? (
          <ActionForm
            action={recordPassengerCountAction.bind(null, shift.id)}
            submitLabel="تسجيل العد"
            variant="secondary"
            className="border-t border-line pt-4"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField name="passengers" label="عدد الركاب" inputMode="numeric" required />
              <TextField
                name="counted_at"
                label="وقت العد"
                type="datetime-local"
                hint="اتركه فارغًا للآن"
              />
              <SelectField
                name="source"
                label="المصدر"
                options={[
                  { value: "SUPERVISOR", label: SOURCE.SUPERVISOR },
                  { value: "DRIVER", label: SOURCE.DRIVER },
                ]}
                required
              />
              <SelectField
                name="confidence"
                label="الدقة"
                options={[
                  { value: "COUNTED", label: CONFIDENCE.COUNTED },
                  { value: "ESTIMATED", label: CONFIDENCE.ESTIMATED },
                ]}
                required
              />
              {shift.sessions.length ? (
                <SelectField
                  name="session_id"
                  label="التشغيل"
                  placeholder="بدون"
                  options={shift.sessions.map((s) => ({
                    value: s.id,
                    label: s.operation_type.name_ar + (s.route ? ` — ${s.route.name}` : ""),
                  }))}
                />
              ) : null}
              <SelectField
                name="direction"
                label="الاتجاه"
                placeholder="غير محدد"
                options={[
                  { value: "OUTBOUND", label: DIRECTION.OUTBOUND },
                  { value: "INBOUND", label: DIRECTION.INBOUND },
                ]}
              />
              <TextField name="note" label="ملاحظة" />
            </div>
          </ActionForm>
        ) : null}
      </CardBody>
    </Card>
  );
}
