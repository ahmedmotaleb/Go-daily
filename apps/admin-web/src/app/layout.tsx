import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
// Inter first (digits, Latin), IBM Plex Sans Arabic for Arabic: see theme.css.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/ibm-plex-sans-arabic/400.css";
import "@fontsource/ibm-plex-sans-arabic/500.css";
import "@fontsource/ibm-plex-sans-arabic/600.css";
import "@fontsource/ibm-plex-sans-arabic/700.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Go Daily — إدارة الأسطول",
    template: "%s | Go Daily",
  },
  description: "نظام Go Daily لإدارة وتشغيل الأسطول",
  robots: { index: false, follow: false },
  icons: { apple: "/apple-touch-icon.png" },
  appleWebApp: { title: "Go Daily", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#082b24",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Every page is rendered per request, so each gets the CSP nonce (U34).
  await connection();
  return (
    <html lang="ar" dir="rtl" className="h-full">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
