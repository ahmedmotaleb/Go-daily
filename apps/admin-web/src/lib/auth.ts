import "server-only";
import { cache } from "react";
import { redirect } from "next/navigation";
import { api } from "./api";
import { getSessionToken } from "./session";
import type { CurrentUser } from "./types";

/** Current user for this request (deduplicated per render). Redirects to login when absent. */
export const getCurrentUser = cache(async (): Promise<CurrentUser> => {
  const token = await getSessionToken();
  if (!token) redirect("/login");
  return api.get<CurrentUser>("/auth/me");
});

export function can(user: Pick<CurrentUser, "permissions">, permission: string): boolean {
  return user.permissions.includes(permission);
}

/** Server-side page guard. The API enforces the same rule; this only avoids a broken page. */
export async function requirePermission(permission: string): Promise<CurrentUser> {
  const user = await getCurrentUser();
  if (!can(user, permission)) redirect("/forbidden");
  return user;
}
