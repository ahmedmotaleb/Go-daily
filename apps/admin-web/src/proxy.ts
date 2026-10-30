import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic auth redirect only: no cookie -> login page. Real session
 * validation happens server-side against the API on every request.
 */
const PUBLIC_PATHS = ["/login", "/auth/clear", "/healthz"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }
  if (!request.cookies.has("gd_session")) {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|icon.svg|icon-.*\\.png|apple-touch-icon.png|robots.txt|favicon.ico|manifest.webmanifest).*)",
  ],
};
