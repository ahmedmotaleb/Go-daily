import { Logo } from "@/components/logo";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <section className="w-full max-w-lg rounded-[var(--radius-card)] border border-line bg-surface p-8 shadow-[var(--shadow-card)]">
        <Logo />
        <h1 className="mt-6 text-2xl font-bold text-ink">نظام إدارة وتشغيل الأسطول</h1>
        <p className="mt-2 text-ink-muted">
          البنية الأساسية جاهزة. سيتم تفعيل تسجيل الدخول ولوحة التحكم في المراحل التالية.
        </p>
      </section>
    </main>
  );
}
