import { SelectField } from "@/components/forms/fields";
import type { OperationType, Route } from "@/lib/types";

/** One select for "operation type" or "operation type — route" (value "typeId|routeId"). */
export function operationOptions(types: OperationType[], routes: Route[]) {
  const out: { value: string; label: string }[] = [];
  for (const t of types) {
    if (t.uses_routes) {
      for (const r of routes.filter((x) => x.operation_type.id === t.id && x.is_active)) {
        out.push({ value: `${t.id}|${r.id}`, label: `${t.name_ar} — ${r.name}` });
      }
    } else {
      out.push({ value: `${t.id}|`, label: t.name_ar });
    }
  }
  return out;
}

export function OperationSelect({
  name,
  label,
  types,
  routes,
  placeholder = "بدون",
  required,
  hint,
}: {
  name: string;
  label: string;
  types: OperationType[];
  routes: Route[];
  placeholder?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <SelectField
      name={name}
      label={label}
      options={operationOptions(types, routes)}
      placeholder={placeholder}
      required={required}
      hint={hint}
    />
  );
}
