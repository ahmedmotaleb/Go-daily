"use client";

import { COMPENSATION_METHOD_LABELS_AR, options, type CompensationMethod } from "@go-daily/shared";
import { useState } from "react";
import { ActionForm } from "@/components/forms/action-form";
import { TextareaField, TextField } from "@/components/forms/fields";
import { Field, Select } from "@/components/ui/field";
import type { FormState } from "@/lib/forms";

const FIELDS: Record<CompensationMethod, string[]> = {
  FIXED_MONTHLY: ["fixed_monthly_amount"],
  DAILY_WAGE: ["daily_wage_amount"],
  REVENUE_PERCENTAGE: ["revenue_percentage"],
  FIXED_PLUS_INCENTIVE: [
    "fixed_monthly_amount",
    "incentive_percentage",
    "incentive_threshold_amount",
  ],
};

export function CompensationPlanForm({
  action,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
}) {
  const [method, setMethod] = useState<CompensationMethod>("FIXED_MONTHLY");
  const show = (f: string) => FIELDS[method].includes(f);
  return (
    <ActionForm
      action={action}
      submitLabel="إضافة الخطة"
      confirm="ستُغلق الخطة الحالية في اليوم السابق لتاريخ البداية. متابعة؟"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="طريقة الاحتساب" htmlFor="method" required>
          <Select
            id="method"
            name="method"
            value={method}
            onChange={(e) => setMethod(e.target.value as CompensationMethod)}
          >
            {options(COMPENSATION_METHOD_LABELS_AR).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>
        <TextField name="effective_from" label="تبدأ من" type="date" required />
        {show("fixed_monthly_amount") ? (
          <TextField
            name="fixed_monthly_amount"
            label="الراتب الشهري (ج.م)"
            inputMode="decimal"
            required
          />
        ) : null}
        {show("daily_wage_amount") ? (
          <TextField name="daily_wage_amount" label="اليومية (ج.م)" inputMode="decimal" required />
        ) : null}
        {show("revenue_percentage") ? (
          <TextField
            name="revenue_percentage"
            label="النسبة من الإيراد المؤهل (%)"
            inputMode="decimal"
            required
          />
        ) : null}
        {show("incentive_percentage") ? (
          <TextField
            name="incentive_percentage"
            label="نسبة الحافز (%)"
            inputMode="decimal"
            required
          />
        ) : null}
        {show("incentive_threshold_amount") ? (
          <TextField
            name="incentive_threshold_amount"
            label="الحافز يُحتسب على الإيراد فوق (ج.م)"
            inputMode="decimal"
            hint="اتركه فارغًا لاحتساب الحافز من أول جنيه"
          />
        ) : null}
      </div>
      <TextareaField name="notes" label="ملاحظات" rows={2} />
    </ActionForm>
  );
}
