import { NextResponse, type NextRequest } from "next/server";
import { env } from "@/lib/env";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * Read-only backend-for-frontend proxy for client-side polling (live map).
 * Only allowlisted GET paths are forwarded; the session token stays in the
 * httpOnly cookie and is attached server-side.
 */
const ALLOWED: RegExp[] = [
  /^tracking\/live$/,
  /^shifts\/[0-9a-f-]{36}\/track$/,
  /^dashboard\/summary$/,
];

export async function GET(request: NextRequest, ctx: RouteContext<"/api/bff/[...path]">) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED.some((re) => re.test(joined))) {
    return NextResponse.json(
      { error: { code: "not_found", message: "غير موجود" } },
      { status: 404 },
    );
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json(
      { error: { code: "not_authenticated", message: "يجب تسجيل الدخول" } },
      { status: 401 },
    );
  }
  const res = await fetch(`${env.apiUrl}/api/v1/${joined}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    cache: "no-store",
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
