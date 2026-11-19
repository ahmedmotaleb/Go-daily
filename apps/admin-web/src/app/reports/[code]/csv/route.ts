import { NextResponse, type NextRequest } from "next/server";
import { env } from "@/lib/env";
import { FILTER_PARAM, REPORT_CODE } from "@/lib/report-types";
import { SESSION_COOKIE } from "@/lib/session";

const ALLOWED = new Set(["date_from", "date_to", ...Object.values(FILTER_PARAM)]);

/** CSV download: forwards the session to the API, which checks the report's permissions. */
export async function GET(request: NextRequest, ctx: RouteContext<"/reports/[code]/csv">) {
  const { code } = await ctx.params;
  if (!REPORT_CODE.test(code)) return new NextResponse("غير موجود", { status: 404 });
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.redirect(new URL("/login", request.url));
  const query = new URLSearchParams();
  for (const [k, v] of request.nextUrl.searchParams) {
    if (ALLOWED.has(k) && /^[0-9a-zA-Z-]{1,40}$/.test(v)) query.set(k, v);
  }
  const res = await fetch(`${env.apiUrl}/api/v1/reports/${code}/csv?${query}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 401) return NextResponse.redirect(new URL("/auth/clear", request.url));
  if (!res.ok) {
    return new NextResponse(res.status === 403 ? "غير مسموح" : "تعذر إنشاء التقرير", {
      status: res.status,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": res.headers.get("content-disposition") ?? "attachment",
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "private, no-store",
    },
  });
}
