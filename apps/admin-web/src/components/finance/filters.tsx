import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";

export type FilterField =
  | { type: "select"; name: string; label: string; options: { value: string; label: string }[] }
  | { type: "date"; name: string; label: string }
  | { type: "checkbox"; name: string; label: string };

/** GET filter form for list pages; values live in the URL. */
export function FilterBar({
  basePath,
  fields,
  values,
}: {
  basePath: string;
  fields: FilterField[];
  values: Record<string, string | undefined>;
}) {
  return (
    <form
      action={basePath}
      className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3"
      role="search"
    >
      {fields.map((f) => (
        <div key={f.name} className="flex flex-col gap-1">
          {f.type === "checkbox" ? (
            <label className="inline-flex h-10 items-center gap-2 text-sm">
              <input
                type="checkbox"
                name={f.name}
                value="true"
                defaultChecked={values[f.name] === "true"}
                className="size-4 accent-forest-700"
              />
              {f.label}
            </label>
          ) : (
            <>
              <label htmlFor={`f-${f.name}`} className="text-xs font-medium text-ink-muted">
                {f.label}
              </label>
              {f.type === "select" ? (
                <Select
                  id={`f-${f.name}`}
                  name={f.name}
                  defaultValue={values[f.name] ?? ""}
                  className="w-44"
                >
                  <option value="">الكل</option>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  id={`f-${f.name}`}
                  name={f.name}
                  type="date"
                  defaultValue={values[f.name]}
                  className="w-40"
                />
              )}
            </>
          )}
        </div>
      ))}
      <Button type="submit" variant="secondary">
        تطبيق
      </Button>
      <Link href={basePath} className="h-10 px-2 text-sm leading-10 text-ink-muted hover:underline">
        مسح
      </Link>
    </form>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "warning" | "danger" | "success";
}) {
  const color =
    tone === "warning"
      ? "text-warning"
      : tone === "danger"
        ? "text-danger"
        : tone === "success"
          ? "text-success"
          : "text-ink";
  return (
    <div className="rounded-[var(--radius-card)] border border-line bg-surface px-4 py-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`ltr-nums mt-1 text-xl font-bold ${color}`}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  );
}

export function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-2 py-2 text-sm">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="font-medium text-ink">{children}</dd>
    </div>
  );
}
