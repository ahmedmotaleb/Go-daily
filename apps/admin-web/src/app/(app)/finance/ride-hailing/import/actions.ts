"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { boundId } from "@/lib/bound";
import { errorToFormState } from "@/lib/form-state";
import type { ImportBatch, ImportPreview } from "@/lib/finance-types";
import type { FormState } from "@/lib/forms";

export type ImportState = FormState & {
  preview?: ImportPreview;
  content?: string;
  fileName?: string;
  platformId?: string;
};

const MAX_BYTES = 1_000_000;

/** The CSV text: a newly chosen file, or the one already previewed. */
async function readInput(formData: FormData): Promise<ImportState | null> {
  const platformId = String(formData.get("platform_id") ?? "");
  const file = formData.get("file");
  if (file instanceof File && file.size > 0) {
    if (file.size > MAX_BYTES) return { ok: false, message: "الملف أكبر من 1 ميجابايت" };
    return { platformId, fileName: file.name, content: await file.text() };
  }
  const content = String(formData.get("content") ?? "");
  if (!content) return { ok: false, message: "اختر ملف CSV" };
  return { platformId, fileName: String(formData.get("file_name") ?? "statement.csv"), content };
}

function mappingFrom(formData: FormData): Record<string, string> | undefined {
  const entries = [...formData.entries()]
    .filter(([k, v]) => k.startsWith("map:") && typeof v === "string" && v !== "")
    .map(([k, v]) => [k.slice(4), String(v)]);
  return entries.length ? Object.fromEntries(entries) : undefined;
}

function body(input: ImportState, formData: FormData) {
  return {
    platform_id: input.platformId,
    file_name: input.fileName,
    content: input.content,
    // A newly chosen file starts from the platform's saved mapping.
    mapping:
      formData.get("file") instanceof File && (formData.get("file") as File).size > 0
        ? undefined
        : mappingFrom(formData),
  };
}

export async function previewImportAction(
  _: ImportState,
  formData: FormData,
): Promise<ImportState> {
  const input = await readInput(formData);
  if (input === null || input.content === undefined) return input ?? {};
  try {
    const preview = await api.post<ImportPreview>(
      "/ride-hailing/imports/preview",
      body(input, formData),
    );
    return { ...input, preview };
  } catch (error) {
    return { ...input, ...errorToFormState(error) };
  }
}

export async function importStatementsAction(
  _: ImportState,
  formData: FormData,
): Promise<ImportState> {
  const input = await readInput(formData);
  if (input === null || input.content === undefined) return input ?? {};
  let batch: ImportBatch;
  try {
    batch = await api.post<ImportBatch>("/ride-hailing/imports", {
      ...body(input, formData),
      mapping: mappingFrom(formData),
    });
  } catch (error) {
    return { ...input, ...errorToFormState(error) };
  }
  revalidatePath("/finance/ride-hailing");
  redirect(`/finance/ride-hailing/imports/${batch.id}?notice=created`);
}

export async function voidImportAction(
  id: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  id = boundId(id);
  try {
    await api.post(`/ride-hailing/imports/${id}/void`, {
      reason: String(formData.get("reason") ?? "").trim(),
    });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/finance/ride-hailing");
  redirect(`/finance/ride-hailing/imports/${id}?notice=record_void`);
}
