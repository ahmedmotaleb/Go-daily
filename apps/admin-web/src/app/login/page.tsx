import type { Metadata } from "next";
import { Logo } from "@/components/logo";
import { Alert } from "@/components/ui/alert";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "تسجيل الدخول" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const sp = await searchParams;
  const expired = sp.expired === "1";
  const next = typeof sp.next === "string" ? sp.next : undefined;
  return (
    <main className="flex min-h-screen items-center justify-center bg-forest-800 p-4">
      <div className="w-full max-w-sm rounded-[var(--radius-card)] bg-surface p-7 shadow-lg">
        <Logo />
        <h1 className="mt-6 text-xl font-bold text-ink">تسجيل الدخول</h1>
        <p className="mt-1 text-sm text-ink-muted">لوحة إدارة وتشغيل الأسطول</p>
        {expired ? (
          <Alert tone="warning" className="mt-4">
            انتهت الجلسة، سجّل الدخول مرة أخرى.
          </Alert>
        ) : null}
        <div className="mt-5">
          <LoginForm next={next} />
        </div>
        <p className="mt-6 text-center text-xs text-ink-muted">
          حسابات السائقين تستخدم تطبيق السائق.
        </p>
      </div>
    </main>
  );
}
