import "server-only";
import { cookies } from "next/headers";
import { env } from "./env";

/**
 * The API session token lives only in an httpOnly cookie; browser
 * JavaScript never sees it. Every API call is made server-side.
 */
export const SESSION_COOKIE = "gd_session";

export async function getSessionToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

export async function setSessionCookie(token: string, expiresAt: string): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: env.cookieSecure,
    sameSite: "lax",
    path: "/",
    expires: new Date(expiresAt),
  });
}

export async function clearSessionCookie(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
