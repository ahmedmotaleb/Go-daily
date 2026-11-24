import { NextResponse, type NextRequest } from "next/server";
import { env } from "@/lib/env";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * Private attachment download. The API checks permissions on the owning
 * record; this route only attaches the session token and passes the file
 * through with headers that stop the browser from executing it.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/files/[id]">) {
  const { id } = await ctx.params;
  if (!/^[0-9a-f-]{36}$/.test(id)) {
    return new NextResponse("غير موجود", { status: 404 });
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.redirect(new URL("/login", request.url));
  const res = await fetch(`${env.apiUrl}/api/v1/attachments/${id}/content`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 401) return NextResponse.redirect(new URL("/auth/clear", request.url));
  if (!res.ok) {
    return new NextResponse(res.status === 403 ? "غير مسموح" : "الملف غير متاح", {
      status: res.status,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new NextResponse(res.body, {
    status: 200,
    headers: {
      "Content-Type": res.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition": res.headers.get("content-disposition") ?? "inline",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
      "Cache-Control": "private, no-store",
    },
  });
}
