import {
  addRouteEventAction,
  recomputeRouteEventsAction,
  voidRouteEventAction,
} from "@/app/(app)/shifts/actions";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { Badge } from "@/components/ui/badge";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import type { OperationSession, RouteEvent } from "@/lib/types";

const EVENT_LABELS: Record<RouteEvent["event_type"], string> = {
  ENTERED: "دخول نطاق",
  EXITED: "خروج من نطاق",
  REACHED_ORIGIN: "الوصول لنقطة البداية",
  REACHED_DESTINATION: "الوصول لنقطة النهاية",
  LEG_COMPLETED: "اكتمال اتجاه",
  LOOP_COMPLETED: "اكتمال دورة",
};

export function RouteEventsPanel({
  session,
  shiftId,
  events,
  canWrite,
}: {
  session: OperationSession;
  shiftId: string;
  events: RouteEvent[];
  canWrite: boolean;
}) {
  const key = events.filter((e) => e.event_type !== "ENTERED" && e.event_type !== "EXITED");
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold">{session.route?.name}</span>
        <Badge tone="active">الدورات: {session.loops}</Badge>
        <Badge tone="info">الاتجاهات: {session.legs}</Badge>
        {canWrite ? (
          <ActionForm
            action={recomputeRouteEventsAction.bind(null, session.id, shiftId)}
            submitLabel="إعادة الاحتساب من GPS"
            variant="ghost"
          />
        ) : null}
      </div>
      {key.length === 0 ? (
        <p className="text-sm text-ink-muted">
          لم يتم اكتشاف وصول للمحطات بعد (تحتاج المحطات إلى إحداثيات ونقاط GPS صالحة).
        </p>
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>الحدث</TH>
              <TH>الوقت</TH>
              <TH>المصدر</TH>
              <TH>الحالة</TH>
              <TH>
                <span className="sr-only">إجراءات</span>
              </TH>
            </tr>
          </THead>
          <tbody>
            {key.map((e) => (
              <TR key={e.id} className={e.status === "VOIDED" ? "opacity-60" : undefined}>
                <TD className="font-medium">
                  {EVENT_LABELS[e.event_type]}
                  {e.sequence_no ? ` #${e.sequence_no}` : ""}
                  {e.direction ? (
                    <span className="text-xs text-ink-muted">
                      {" "}
                      ({e.direction === "OUTBOUND" ? "ذهاب" : "عودة"})
                    </span>
                  ) : null}
                </TD>
                <TD className="text-ink-muted">{formatDateTime(e.occurred_at)}</TD>
                <TD>{e.source === "AUTO" ? "تلقائي (GPS)" : `يدوي: ${e.reason ?? ""}`}</TD>
                <TD>
                  {e.status === "ACTIVE" ? (
                    <Badge tone="success">معتمد</Badge>
                  ) : (
                    <Badge>ملغى{e.void_reason ? `: ${e.void_reason}` : ""}</Badge>
                  )}
                </TD>
                <TD>
                  {canWrite && e.status === "ACTIVE" ? (
                    <details>
                      <summary className="cursor-pointer text-xs text-ink-muted">إلغاء</summary>
                      <ActionForm
                        action={voidRouteEventAction.bind(null, e.id, shiftId)}
                        submitLabel="تأكيد الإلغاء"
                        variant="secondary"
                        className="mt-2"
                      >
                        <TextField name="reason" label="السبب" required />
                      </ActionForm>
                    </details>
                  ) : null}
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}
      {canWrite ? (
        <details>
          <summary className="cursor-pointer text-sm font-medium text-forest-700">
            إضافة حدث يدويًا (مع ذكر السبب)
          </summary>
          <ActionForm
            action={addRouteEventAction.bind(null, session.id, shiftId)}
            submitLabel="إضافة"
            variant="secondary"
            className="mt-3"
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <SelectField
                name="event_type"
                label="الحدث"
                defaultValue="LOOP_COMPLETED"
                options={[
                  { value: "LOOP_COMPLETED", label: EVENT_LABELS.LOOP_COMPLETED },
                  { value: "LEG_COMPLETED", label: EVENT_LABELS.LEG_COMPLETED },
                  { value: "REACHED_DESTINATION", label: EVENT_LABELS.REACHED_DESTINATION },
                  { value: "REACHED_ORIGIN", label: EVENT_LABELS.REACHED_ORIGIN },
                ]}
              />
              <TextField name="occurred_at" label="الوقت" type="datetime-local" required />
              <TextField name="reason" label="السبب" required />
            </div>
          </ActionForm>
        </details>
      ) : null}
    </div>
  );
}
