"use client";

import { useState } from "react";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextField } from "@/components/forms/fields";
import { Select } from "@/components/ui/field";
import { LEDGER_TYPE_LABELS, options } from "@/lib/finance-labels";
import type { LedgerEntryType } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";

const HINTS: Partial<Record<LedgerEntryType, string>> = {
  CASH_HANDOVER: "السائق سلّم نقدية للشركة (يقلل ما عليه)",
  ADVANCE: "سلفة مدفوعة للسائق (عليه)",
  PAYMENT: "صرف مستحقات للسائق (يقلل ما له)",
  BONUS: "مكافأة مستحقة للسائق (له)",
  DEDUCTION: "خصم على السائق — السبب مطلوب",
  ADJUSTMENT: "تسوية يدوية — الاتجاه والسبب مطلوبان",
};

const MANUAL_TYPES = options(LEDGER_TYPE_LABELS, ["EARNING", "REIMBURSEMENT", "CASH_COLLECTED"]);

export function LedgerForm({
  action,
}: {
  action: (s: FormState, f: FormData) => Promise<FormState>;
}) {
  const [type, setType] = useState<LedgerEntryType>("CASH_HANDOVER");
  return (
    <ActionForm action={action} submitLabel="إضافة القيد" variant="accent">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="entry_type" className="text-sm font-medium text-ink">
            نوع القيد
          </label>
          <Select
            id="entry_type"
            name="entry_type"
            value={type}
            onChange={(e) => setType(e.target.value as LedgerEntryType)}
          >
            {MANUAL_TYPES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <p className="text-xs text-ink-muted">{HINTS[type]}</p>
        </div>
        <TextField name="amount" label="المبلغ" inputMode="decimal" required />
        <TextField name="occurred_on" label="التاريخ" type="date" required />
        <TextField name="description" label="البيان" required />
        {type === "ADJUSTMENT" ? (
          <SelectField
            name="direction"
            label="الاتجاه"
            options={[
              { value: "CREDIT", label: "للسائق (له)" },
              { value: "DEBIT", label: "على السائق (عليه)" },
            ]}
            placeholder="اختر"
            required
          />
        ) : null}
        {type === "ADJUSTMENT" || type === "DEDUCTION" ? (
          <TextField name="reason" label="السبب" required className="sm:col-span-2" />
        ) : null}
      </div>
    </ActionForm>
  );
}
