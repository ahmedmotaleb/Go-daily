import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <h1 className="text-xl font-bold text-ink">الصفحة غير موجودة</h1>
      <p className="text-sm text-ink-muted">ربما تم نقل العنصر أو أن الرابط غير صحيح.</p>
      <Link href="/" className="text-sm font-medium text-forest-700 hover:underline">
        العودة للوحة التحكم
      </Link>
    </main>
  );
}
