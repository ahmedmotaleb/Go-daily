"use server";

import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";

/**
 * U47: sends only the values that differ from the current policy. An
 * emptied field goes back to the environment default.
 */
export async function updatePoliciesAction(
  current: Record<string, number>,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = formValues(formData);
  const changes: Record<string, number | null> = {};
  for (const [key, was] of Object.entries(current)) {
    const raw = String(formData.get(key) ?? "").trim();
    if (raw === "") {
      changes[key] = null;
      continue;
    }
    const next = Number(raw.replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d))));
    if (Number.isNaN(next)) return { ok: false, fieldErrors: { [key]: "أدخل رقمًا" }, values };
    if (next !== was) changes[key] = next;
  }
  const reason = String(formData.get("reason") ?? "").trim();
  if (Object.keys(changes).length === 0) {
    return { ok: false, message: "لا يوجد تغيير", values };
  }
  try {
    await api.post("/policies", { changes, reason });
  } catch (error) {
    return errorToFormState(error, values);
  }
  revalidatePath("/policies");
  return { ok: true, message: "حُفظت نسخة جديدة من السياسة" };
}
