"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import type { AttachmentOwner, UploadResult } from "@/lib/attachment-types";
import { boundId, boundOneOf, boundReturnPath } from "@/lib/bound";
import { errorToFormState } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { withNotice } from "@/lib/notices";
import { text } from "@/lib/parse";

const OWNERS: AttachmentOwner[] = [
  "fuel_transaction",
  "expense",
  "revenue_entry",
  "ride_hailing_statement",
  "maintenance_record",
  "vehicle",
];

export async function uploadAttachmentAction(
  ownerType: AttachmentOwner,
  ownerId: string,
  returnPath: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  ownerType = boundOneOf(ownerType, OWNERS);
  ownerId = boundId(ownerId);
  returnPath = boundReturnPath(returnPath);
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, message: "اختر ملفًا", fieldErrors: { file: "اختر ملفًا" } };
  }
  const form = new FormData();
  form.set("owner_type", ownerType);
  form.set("owner_id", ownerId);
  form.set("file", file, file.name);
  let result: UploadResult;
  try {
    result = await api.upload<UploadResult>("/attachments", form);
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath(returnPath);
  redirect(
    withNotice(returnPath, result.duplicates.length ? "attachment_duplicate" : "attachment_added"),
  );
}

export async function deleteAttachmentAction(
  attachmentId: string,
  returnPath: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  attachmentId = boundId(attachmentId);
  returnPath = boundReturnPath(returnPath);
  try {
    await api.post(`/attachments/${attachmentId}/delete`, {
      reason: text(formData, "reason") ?? "",
    });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath(returnPath);
  redirect(withNotice(returnPath, "attachment_deleted"));
}
