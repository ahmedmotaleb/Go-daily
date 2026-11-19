"use client";

import { useActionState } from "react";
import {
  type ImportState,
  importStatementsAction,
  previewImportAction,
} from "@/app/(app)/finance/ride-hailing/import/actions";
import { Alert } from "@/components/ui/alert";
import { Badge, type Tone } from "@/components/ui/badge";
import { SubmitButton } from "@/components/ui/submit-button";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";

const STATUS: Record<"OK" | "ERROR" | "DUPLICATE", { label: string; tone: Tone }> = {
  OK: { label: "جاهز", tone: "success" },
  ERROR: { label: "خطأ", tone: "danger" },
  DUPLICATE: { label: "مكرر", tone: "warning" },
};

const control =
  "block w-full rounded-[var(--radius-input)] border border-line bg-surface px-3 py-2 text-sm";

export function StatementImport({ platforms }: { platforms: { value: string; label: string }[] }) {
  const [state, preview] = useActionState<ImportState, FormData>(previewImportAction, {});
  const [importState, commit] = useActionState<ImportState, FormData>(importStatementsAction, {});
  const p = state.preview;
  const hidden = (
    <>
      <input type="hidden" name="platform_id" value={state.platformId ?? ""} />
      <input type="hidden" name="file_name" value={state.fileName ?? ""} />
      <input type="hidden" name="content" value={state.content ?? ""} />
    </>
  );
  const mappingSelects = p ? (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {p.fields.map((f) => (
        <label key={f.key} className="block text-sm">
          <span className="mb-1 block font-medium">
            {f.label}
            {f.required ? <span className="text-danger"> *</span> : null}
          </span>
          <select name={`map:${f.key}`} defaultValue={p.mapping[f.key] ?? ""} className={control}>
            <option value="">— غير موجود —</option>
            {p.headers.map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  ) : null;

  return (
    <div className="space-y-6">
      <form action={preview} className="space-y-4" key={`${state.fileName}|${p?.file_name}`}>
        {state.message ? <Alert tone="danger">{state.message}</Alert> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">المنصة *</span>
            <select
              name="platform_id"
              defaultValue={state.platformId ?? ""}
              className={control}
              required
            >
              <option value="">اختر المنصة</option>
              {platforms.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">ملف الكشف (CSV) *</span>
            <input type="file" name="file" accept=".csv,text/csv" className={control} />
            <span className="mt-1 block text-xs text-ink-muted">
              {state.fileName
                ? `الملف الحالي: ${state.fileName} — اختر ملفًا آخر لاستبداله`
                : "حتى 1 ميجابايت و2000 صف؛ تصدير الكشف من المنصة نفسها"}
            </span>
          </label>
        </div>
        <input type="hidden" name="file_name" value={state.fileName ?? ""} />
        <input type="hidden" name="content" value={state.content ?? ""} />
        {mappingSelects ? (
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">أعمدة الملف</legend>
            {mappingSelects}
          </fieldset>
        ) : null}
        <div className="flex justify-end">
          <SubmitButton variant="secondary" pendingLabel="جارٍ الفحص…">
            {p ? "إعادة الفحص" : "فحص الملف"}
          </SubmitButton>
        </div>
      </form>

      {p ? (
        <form action={commit} className="space-y-4">
          {hidden}
          {/* Import exactly what was checked: change columns, then check again. */}
          {Object.entries(p.mapping).map(([k, v]) => (
            <input key={k} type="hidden" name={`map:${k}`} value={v} />
          ))}
          {importState.message ? <Alert tone="danger">{importState.message}</Alert> : null}
          {p.already_imported ? (
            <Alert tone="warning">
              هذا الملف مستورد من قبل لهذه المنصة. ألغِ الاستيراد السابق أولًا إذا كان خاطئًا.
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2 text-sm">
            <Badge tone="success">جاهز: {formatNumber(p.counts.OK)}</Badge>
            <Badge tone="danger">أخطاء: {formatNumber(p.counts.ERROR)}</Badge>
            <Badge tone="warning">مكرر: {formatNumber(p.counts.DUPLICATE)}</Badge>
            <Badge tone="info">تحتاج مراجعة: {formatNumber(p.counts.warnings)}</Badge>
          </div>
          <div className="overflow-x-auto rounded-[var(--radius-card)] border border-line">
            <Table>
              <THead>
                <tr>
                  <TH>الصف</TH>
                  <TH>الحالة</TH>
                  <TH>السائق</TH>
                  <TH>السيارة</TH>
                  <TH>الفترة</TH>
                  <TH>الإجمالي</TH>
                  <TH>العمولة</TH>
                  <TH>الصافي</TH>
                  <TH>ملاحظات</TH>
                </tr>
              </THead>
              <tbody>
                {p.rows.map((r) => (
                  <TR key={r.row}>
                    <TD className="ltr-nums">{r.row}</TD>
                    <TD>
                      <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
                    </TD>
                    <TD>{r.driver ?? "—"}</TD>
                    <TD className="ltr-nums">{r.vehicle ?? "—"}</TD>
                    <TD className="ltr-nums">
                      {r.period_start ? formatDate(r.period_start) : "—"}
                      {r.period_end && r.period_end !== r.period_start
                        ? ` — ${formatDate(r.period_end)}`
                        : ""}
                    </TD>
                    <TD className="ltr-nums">{formatMoney(r.gross_earnings)}</TD>
                    <TD className="ltr-nums">{formatMoney(r.platform_fees)}</TD>
                    <TD className="ltr-nums">{formatMoney(r.net_earnings)}</TD>
                    <TD className="text-xs">{[...r.messages, ...r.warnings].join("؛ ") || "—"}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
          <div className="flex items-center justify-end gap-3">
            <span className="text-xs text-ink-muted">
              الصفوف الجاهزة تُسجل كشوفًا بانتظار المراجعة؛ الباقي يُحفظ في سجل الاستيراد
            </span>
            {p.counts.OK > 0 && !p.already_imported ? (
              <SubmitButton variant="accent" pendingLabel="جارٍ الاستيراد…">
                استيراد {formatNumber(p.counts.OK)} صف
              </SubmitButton>
            ) : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}
