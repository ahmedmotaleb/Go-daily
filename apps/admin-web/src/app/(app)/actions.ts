"use server";

import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { clearSessionCookie, getSessionToken } from "@/lib/session";

export async function logoutAction(): Promise<void> {
  if (await getSessionToken()) {
    try {
      await api.post("/auth/logout");
    } catch {
      // The cookie is cleared regardless; an already-invalid session is fine.
    }
  }
  await clearSessionCookie();
  redirect("/login");
}
