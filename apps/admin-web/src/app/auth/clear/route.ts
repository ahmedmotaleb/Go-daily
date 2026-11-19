import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

/** Clears a session cookie the API no longer accepts, then returns to the login page. */
export function GET(request: NextRequest) {
  const res = NextResponse.redirect(new URL("/login?expired=1", request.url));
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
