"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { boundId } from "@/lib/bound";
import type { ExceptionRun, ExceptionStatus } from "@/lib/exception-types";
import { errorToFormState, formValues } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { withNotice } from "@/lib/notices";
import { text } from "@/lib/parse";

const STATUSES: ExceptionStatus[] = [
  "OPEN",
  "UNDER_REVIEW",
  "EXPLAINED",
  "CORRECTED",
  "DISMISSED",
  "ESCALATED",
];

export async function runDetectionAction(_: FormState, formData: FormData): Promise<FormState> {
  const days = Number(text(formData, "days") ?? "3");
  let run: ExceptionRun;
  try {
    run = await api.post<ExceptionRun>("/exceptions/run", {
      days: Number.isInteger(days) && days >= 1 && days <= 31 ? days : 3,
    });
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/exceptions");
  redirect(
    withNotice(
      "/exceptions",
      Object.keys(run.errors).length ? "exceptions_run_partial" : "exceptions_run",
    ),
  );
}

export async function reviewExceptionAction(
  exceptionId: string,
  _: FormState,
  formData: FormData,
): Promise<FormState> {
  exceptionId = boundId(exceptionId);
  const status = text(formData, "status");
  if (!status || !STATUSES.includes(status as ExceptionStatus)) {
    return { ok: false, message: "اختر الإجراء", fieldErrors: { status: "اختر الإجراء" } };
  }
  try {
    await api.post(`/exceptions/${exceptionId}/review`, {
      status,
      notes: text(formData, "notes"),
      resolution: text(formData, "resolution"),
    });
  } catch (error) {
    return errorToFormState(error, formValues(formData));
  }
  revalidatePath("/exceptions");
  revalidatePath(`/exceptions/${exceptionId}`);
  redirect(withNotice(`/exceptions/${exceptionId}`, "exception_reviewed"));
}
