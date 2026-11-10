"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { boundId } from "@/lib/bound";
import { errorToFormState } from "@/lib/form-state";
import type { FormState } from "@/lib/forms";
import { type AppNotification, safeInternalLink } from "@/lib/notification-types";
import { withNotice } from "@/lib/notices";

/** Marks the notification read, then opens the page it points to. */
export async function openNotificationAction(notificationId: string): Promise<void> {
  notificationId = boundId(notificationId);
  const n = await api.post<AppNotification>(`/notifications/${notificationId}/read`);
  revalidatePath("/", "layout");
  redirect(safeInternalLink(n.link) ?? "/notifications");
}

export async function markAllReadAction(): Promise<FormState> {
  try {
    await api.post("/notifications/read-all");
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/", "layout");
  redirect(withNotice("/notifications", "notifications_read"));
}

export async function generateNotificationsAction(): Promise<FormState> {
  try {
    await api.post("/notifications/generate");
  } catch (error) {
    return errorToFormState(error);
  }
  revalidatePath("/", "layout");
  redirect(withNotice("/notifications", "notifications_generated"));
}
