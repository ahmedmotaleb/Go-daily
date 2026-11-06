"use server";

import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { boundId } from "@/lib/bound";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { decimal, text } from "@/lib/parse";

/** «تأكيد: تم التحصيل»: cash actually received; the API caps it at what is owed. */
export async function collectCashAction(
  driverId: string,
  closeoutId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  driverId = boundId(driverId);
  closeoutId = boundId(closeoutId);
  const amount = decimal(formData, "amount");
  if (!amount || Number(amount) <= 0) {
    return {
      ok: false,
      message: "أدخل المبلغ اللي اتحصّل",
      fieldErrors: { amount: "أدخل مبلغًا أكبر من صفر" },
      values: formValues(formData),
    };
  }
  try {
    await api.post("/cash/collections", {
      driver_id: driverId,
      closeout_id: closeoutId,
      amount,
      note: text(formData, "note"),
    });
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/cash");
  return { ok: true, message: "تم تسجيل التحصيل" };
}

export async function voidCollectionAction(
  collectionId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  collectionId = boundId(collectionId);
  const reason = text(formData, "reason");
  if (!reason || reason.length < 3) {
    return { ok: false, message: "اكتب سبب الإلغاء", fieldErrors: { reason: "اكتب السبب" } };
  }
  try {
    await api.post(`/cash/collections/${collectionId}/void`, { reason });
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/cash");
  return { ok: true, message: "تم إلغاء التحصيل" };
}
