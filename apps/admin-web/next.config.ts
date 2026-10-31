import path from "node:path";
import type { NextConfig } from "next";

// The browser only talks to this server (the API is called server-side), so
// scripts, styles and requests stay same-origin. Map tiles are images from
// the configured tile server. 'unsafe-inline' is needed by Next.js inline
// bootstrap scripts without nonces; 'unsafe-eval' only in development.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "production" ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image.
  output: "standalone",
  // Trace workspace packages from the monorepo root.
  outputFileTracingRoot: path.join(__dirname, "../../"),
  poweredByHeader: false,
  experimental: {
    // Receipt and invoice uploads (the API caps files at 10 MB).
    serverActions: { bodySizeLimit: "11mb" },
  },
  reactStrictMode: true,
  turbopack: {
    root: path.join(__dirname, "../../"),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
