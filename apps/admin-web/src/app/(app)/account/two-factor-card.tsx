"use client";

import { useRouter } from "next/navigation";
import { useActionState } from "react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { SubmitButton } from "@/components/ui/submit-button";
import {
  type TwoFactorState,
  twoFactorCodesAction,
  twoFactorDisableAction,
  twoFactorFlowAction,
} from "./actions";

type Status = { enabled: boolean; required: boolean; recovery_codes_left: number };

function CodeInput({ error }: { error?: string }) {
  return (
    <Field label="الرمز من تطبيق المصادقة" htmlFor="code" required error={error}>
      <Input
        id="code"
        name="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        className="ltr-nums"
        required
      />
    </Field>
  );
}

function RecoveryCodes({ codes }: { codes: string[] }) {
  const router = useRouter();
  return (
    <div className="space-y-3">
      <Alert tone="warning">
        احفظ رموز الاسترداد في مكان آمن الآن؛ لن تظهر مرة أخرى. كل رمز يُستخدم مرة واحدة إذا فقدت
        هاتفك.
      </Alert>
      <ol className="ltr-nums bg-page grid grid-cols-2 gap-2 rounded-[var(--radius-control)] border border-line p-3 font-mono text-sm">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ol>
      <Button type="button" onClick={() => router.refresh()}>
        حفظت الرموز
      </Button>
    </div>
  );
}

function Setup() {
  const [state, formAction] = useActionState(twoFactorFlowAction, {} as TwoFactorState);
  if (state.stage === "codes" && state.codes) return <RecoveryCodes codes={state.codes} />;
  if (state.stage === "scan" && state.qr) {
    return (
      <form action={formAction} className="space-y-4" noValidate>
        {state.error ? <Alert tone="danger">{state.error}</Alert> : null}
        <p className="text-sm text-ink-soft">
          1. امسح الرمز بتطبيق مصادقة (مثل Google Authenticator أو Microsoft Authenticator). 2. أدخل
          الرمز المكوّن من 6 أرقام الذي يظهر في التطبيق.
        </p>
        {/* eslint-disable-next-line @next/next/no-img-element -- generated on the server */}
        <img src={state.qr} alt="رمز QR لإعداد التحقق بخطوتين" width={200} height={200} />
        <p className="text-xs text-ink-muted">
          أو أدخل المفتاح يدويًا: <span className="ltr-nums font-mono">{state.secret}</span>
        </p>
        <CodeInput error={state.fieldErrors?.code} />
        <SubmitButton pendingLabel="جارٍ التحقق…">تفعيل</SubmitButton>
      </form>
    );
  }
  return (
    <form action={formAction} className="space-y-3">
      {state.error ? <Alert tone="danger">{state.error}</Alert> : null}
      <input type="hidden" name="op" value="start" />
      <p className="text-sm text-ink-soft">
        بعد التفعيل يطلب الدخول رمزًا من تطبيق على هاتفك بالإضافة إلى كلمة المرور.
      </p>
      <SubmitButton pendingLabel="جارٍ الإعداد…">بدء الإعداد</SubmitButton>
    </form>
  );
}

function Reauth({
  action,
  label,
  critical,
}: {
  action: (s: TwoFactorState, f: FormData) => Promise<TwoFactorState>;
  label: string;
  critical?: boolean;
}) {
  const [state, formAction] = useActionState(action, {});
  if (state.stage === "codes" && state.codes) return <RecoveryCodes codes={state.codes} />;
  return (
    <form action={formAction} className="space-y-3" noValidate>
      {state.error ? <Alert tone="danger">{state.error}</Alert> : null}
      <Field
        label="كلمة المرور"
        htmlFor={`${label}-password`}
        required
        error={state.fieldErrors?.password}
      >
        <Input
          id={`${label}-password`}
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
      </Field>
      <CodeInput error={state.fieldErrors?.code} />
      <SubmitButton variant={critical ? "danger" : "secondary"} pendingLabel="جارٍ التنفيذ…">
        {label}
      </SubmitButton>
    </form>
  );
}

export function TwoFactorCard({ status }: { status: Status }) {
  return (
    <Card className="max-w-xl">
      <CardHeader
        title="التحقق بخطوتين"
        description={
          status.required
            ? "مطلوب لصلاحيتك: يحمي الحساب حتى لو عُرفت كلمة المرور."
            : "اختياري: يحمي الحساب حتى لو عُرفت كلمة المرور."
        }
        actions={
          <Badge tone={status.enabled ? "success" : status.required ? "warning" : "neutral"} dot>
            {status.enabled ? "مفعل" : "غير مفعل"}
          </Badge>
        }
      />
      <CardBody className="space-y-6">
        {status.enabled ? (
          <>
            <p className="text-sm text-ink-soft">
              رموز الاسترداد المتبقية:{" "}
              <span className="ltr-nums">{status.recovery_codes_left}</span>
            </p>
            <details className="space-y-3">
              <summary className="cursor-pointer text-sm font-semibold text-primary">
                إصدار رموز استرداد جديدة
              </summary>
              <div className="pt-3">
                <Reauth action={twoFactorCodesAction} label="إصدار رموز جديدة" />
              </div>
            </details>
            {!status.required ? (
              <details className="space-y-3">
                <summary className="cursor-pointer text-sm font-semibold text-danger">
                  إيقاف التحقق بخطوتين
                </summary>
                <div className="pt-3">
                  <Reauth action={twoFactorDisableAction} label="إيقاف" critical />
                </div>
              </details>
            ) : null}
          </>
        ) : (
          <Setup />
        )}
      </CardBody>
    </Card>
  );
}
