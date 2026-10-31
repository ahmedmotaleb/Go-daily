import type { MetadataRoute } from "next";

/**
 * Installable admin app (home screen / desktop window). There is no offline
 * mode on purpose: every screen shows live operational and financial data,
 * and a stale cached copy would be misleading.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Go Daily — إدارة الأسطول والتشغيل",
    short_name: "Go Daily",
    description: "متابعة المركبات والسائقين والتشغيل والحسابات",
    lang: "ar",
    dir: "rtl",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#f0f2ee",
    theme_color: "#123b2b",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
