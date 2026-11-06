"use client";

import { Info } from "lucide-react";
import { useActionState, useEffect, useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import { egp, remainingAfter } from "@/lib/cash";
import { initialFormState, type FormState } from "@/lib/forms";

type Action = (state: FormState, formData: FormData) => Promise<FormState>;

/**
 * «تسجيل تحصيل»: what the driver owes today (this close-out plus anything
 * carried from earlier days) and the amount actually received. The rest
 * stays due and carries over.
 */
export function CollectDialog({
  action,
  driverName,
  subtitle,
  net,
  carried,
  collected,
  totalDue,
}: {
  action: Action;
  driverName: string;
  subtitle: string;
  net: string;
  carried: string;
  /** Already collected on this close-out. */
  collected: string;
  /** What is still due now (carried + net - collected). */
  totalDue: string;
}) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState(String(Number(totalDue)));
  const [state, formAction] = useActionState(action, initialFormState);
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const rest = remainingAfter(totalDue, amount);
  const close = () => {
    setOpen(false);
    opener.current?.focus();
  };

  // A successful save closes the dialog (the board revalidates behind it).
  const [handled, setHandled] = useState(state);
  if (handled !== state) {
    setHandled(state);
    if (state.ok) setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        opener.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <Button
        ref={opener}
        variant="accent"
        className="w-full"
        onClick={() => {
          setAmount(String(Number(totalDue)));
          setOpen(true);
        }}
      >
        تسجيل التحصيل
      </Button>
      {open ? (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-[rgb(8_43_36/0.5)] p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) close();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="collect-title"
            className="flex w-full max-w-[460px] flex-col gap-4 rounded-[24px] bg-surface p-6 shadow-[0_24px_60px_rgb(8_43_36/0.3)]"
          >
            <div className="flex flex-col gap-1">
              <h2 id="collect-title" className="text-xl font-bold">
                تسجيل تحصيل — {driverName}
              </h2>
              <span className="text-[13px] text-ink-muted">{subtitle}</span>
            </div>
            <dl className="flex flex-col gap-2 rounded-[14px] bg-neutral-50 px-3.5 py-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-ink-soft">صافي اليوم</dt>
                <dd className="font-semibold">{egp(net)} ج.م</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-soft">متبقي من أيام سابقة</dt>
                <dd className="font-semibold">{egp(carried)} ج.م</dd>
              </div>
              {Number(collected) > 0 ? (
                <div className="flex justify-between">
                  <dt className="text-ink-soft">تم تحصيله من قبل</dt>
                  <dd className="font-semibold text-success">− {egp(collected)} ج.م</dd>
                </div>
              ) : null}
              <div className="h-px bg-line" aria-hidden="true" />
              <div className="flex justify-between">
                <dt className="font-bold">الإجمالي المستحق</dt>
                <dd className="font-bold">{egp(totalDue)} ج.م</dd>
              </div>
            </dl>
            <form action={formAction} className="flex flex-col gap-4" noValidate>
              {state.message && !state.ok && !state.fieldErrors?.amount ? (
                <Alert tone="danger">{state.message}</Alert>
              ) : null}
              <Field
                label="المبلغ اللي اتحصّل فعلًا (ج.م)"
                htmlFor="amount"
                error={state.fieldErrors?.amount}
              >
                <Input
                  ref={input}
                  id="amount"
                  name="amount"
                  inputMode="decimal"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  invalid={!!state.fieldErrors?.amount}
                  className="h-14 text-xl font-bold"
                />
              </Field>
              <div
                role="status"
                className={
                  rest > 0
                    ? "flex items-center justify-between rounded-[14px] bg-danger-soft px-3.5 py-3 text-danger"
                    : "flex items-center justify-between rounded-[14px] bg-success-soft px-3.5 py-3 text-success"
                }
              >
                <span className="text-sm font-semibold">المتبقي لم يُحصَّل</span>
                <span className="text-lg font-bold">{egp(rest)} ج.م</span>
              </div>
              <Field label="ملاحظة للسائق (اختياري)" htmlFor="note">
                <Input
                  id="note"
                  name="note"
                  maxLength={300}
                  placeholder="مثال: الباقي يُسلَّم مع تقفيل الخميس"
                  defaultValue={state.values?.note}
                />
              </Field>
              <p className="flex items-center gap-2 text-xs text-ink-muted">
                <Info className="size-4 shrink-0" aria-hidden="true" />
                المبلغ المحصّل والمتبقي يظهران للسائق في «حسابي» فور التأكيد.
              </p>
              <SubmitButton variant="primary" className="h-[52px]" pendingLabel="جارٍ التسجيل…">
                تأكيد: تم التحصيل
              </SubmitButton>
              <Button variant="secondary" onClick={close}>
                إلغاء
              </Button>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
