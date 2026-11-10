import { NextResponse, type NextRequest } from "next/server";

/**
 * Two jobs on every page request:
 *
 * 1. Content Security Policy with a fresh nonce (U34). Next.js reads the
 *    policy from the request headers and puts the nonce on its own scripts,
 *    so no inline script without it can run. Style attributes stay allowed
 *    (style-src-attr): React and the map library position elements with them.
 * 2. Optimistic auth redirect only: no cookie -> login page. Real session
 *    validation happens server-side against the API on every request.
 */
const PUBLIC_PATHS = ["/login", "/auth/clear", "/healthz"];

export function contentSecurityPolicy(nonce: string, dev: boolean): string {
  return [
    "default-src 'self'",
    // 'strict-dynamic': scripts loaded by a trusted (nonced) script are trusted.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Style elements need the nonce; dev mode injects unnonced <style> tags for hot reload.
    `style-src 'self' ${dev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

function withCsp(request: NextRequest, response?: (headers: Headers) => NextResponse) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = contentSecurityPolicy(nonce, process.env.NODE_ENV !== "production");
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp);
  const res = response ? response(headers) : NextResponse.next({ request: { headers } });
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return withCsp(request);
  }
  if (!request.cookies.has("gd_session")) {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
    return withCsp(request, () => NextResponse.redirect(url));
  }
  return withCsp(request);
}

export const config = {
  matcher: [
    {
      source:
        "/((?!_next/static|_next/image|brand/|icon.svg|icon-.*\\.png|apple-touch-icon.png|robots.txt|favicon.ico|manifest.webmanifest).*)",
      // Prefetches do not render HTML that needs a nonce.
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
