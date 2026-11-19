export default function Loading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <div className="h-8 w-48 animate-pulse rounded bg-neutral-200" />
      <div className="h-40 animate-pulse rounded-[var(--radius-card)] bg-neutral-200/70" />
      <span className="sr-only">جارٍ التحميل…</span>
    </div>
  );
}
