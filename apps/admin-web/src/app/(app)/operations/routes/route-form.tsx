"use client";

import {
  TRIP_PATTERN_LABELS_AR,
  WEEKDAY_LABELS_AR,
  WEEKDAY_ORDER,
  options,
} from "@go-daily/shared";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { ActionForm, useActionFormState } from "@/components/forms/action-form";
import { SelectField, TextareaField, TextField } from "@/components/forms/fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import type { FormState } from "@/lib/forms";
import type { OperationType, Route, RouteStop } from "@/lib/types";

type StopDraft = { key: number; name: string; lat: string; lng: string; radius: string };

function toDraft(s: RouteStop, key: number): StopDraft {
  return {
    key,
    name: s.name,
    lat: s.latitude ?? "",
    lng: s.longitude ?? "",
    radius: String(s.radius_m),
  };
}

function StopFields({ prefix, title, stop }: { prefix: string; title: string; stop?: RouteStop }) {
  return (
    <fieldset className="rounded-[var(--radius-control)] border border-line p-3">
      <legend className="px-1 text-sm font-semibold text-ink">{title}</legend>
      <div className="grid gap-3 sm:grid-cols-4">
        <TextField
          name={`${prefix}_name`}
          label="الاسم"
          defaultValue={stop?.name}
          required
          className="sm:col-span-4"
        />
        <TextField
          name={`${prefix}_lat`}
          label="خط العرض"
          defaultValue={stop?.latitude}
          inputMode="decimal"
          placeholder="31.0409"
        />
        <TextField
          name={`${prefix}_lng`}
          label="خط الطول"
          defaultValue={stop?.longitude}
          inputMode="decimal"
          placeholder="31.3785"
        />
        <TextField
          name={`${prefix}_radius`}
          label="نصف القطر (م)"
          defaultValue={stop?.radius_m ?? 150}
          inputMode="numeric"
        />
      </div>
    </fieldset>
  );
}

function IntermediateStops({ initial }: { initial: StopDraft[] }) {
  const state = useActionFormState();
  const [stops, setStops] = useState<StopDraft[]>(() => {
    const echoed = state.values?.__stops;
    if (!echoed) return initial;
    try {
      const parsed = JSON.parse(echoed) as {
        name?: string;
        latitude?: string;
        longitude?: string;
        radius_m?: number;
      }[];
      return parsed.map((s, i) => ({
        key: i + 1,
        name: s.name ?? "",
        lat: s.latitude ?? "",
        lng: s.longitude ?? "",
        radius: s.radius_m ? String(s.radius_m) : "150",
      }));
    } catch {
      return initial;
    }
  });
  const [nextKey, setNextKey] = useState(100);
  const error = Object.entries(state.fieldErrors ?? {}).find(([k]) =>
    k.startsWith("intermediate_stops"),
  )?.[1];
  return (
    <fieldset className="rounded-[var(--radius-control)] border border-line p-3">
      <legend className="px-1 text-sm font-semibold text-ink">نقاط توقف وسيطة (اختياري)</legend>
      {stops.length === 0 ? <p className="text-sm text-ink-muted">لا توجد نقاط وسيطة.</p> : null}
      <ol className="space-y-2">
        {stops.map((s, i) => (
          <li key={s.key} className="grid items-end gap-2 sm:grid-cols-[2fr_1fr_1fr_1fr_auto]">
            <Input
              name="stop_name"
              aria-label={`اسم النقطة ${i + 1}`}
              defaultValue={s.name}
              placeholder={`نقطة ${i + 1}`}
            />
            <Input
              name="stop_lat"
              aria-label="خط العرض"
              defaultValue={s.lat}
              inputMode="decimal"
              placeholder="خط العرض"
            />
            <Input
              name="stop_lng"
              aria-label="خط الطول"
              defaultValue={s.lng}
              inputMode="decimal"
              placeholder="خط الطول"
            />
            <Input
              name="stop_radius"
              aria-label="نصف القطر"
              defaultValue={s.radius}
              inputMode="numeric"
              placeholder="150"
            />
            <Button
              variant="ghost"
              size="sm"
              aria-label="حذف النقطة"
              onClick={() => setStops((prev) => prev.filter((x) => x.key !== s.key))}
            >
              <Trash2 className="size-4" />
            </Button>
          </li>
        ))}
      </ol>
      {error ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
      <Button
        variant="secondary"
        size="sm"
        className="mt-3"
        onClick={() => {
          setStops((prev) => [
            ...prev,
            { key: nextKey, name: "", lat: "", lng: "", radius: "150" },
          ]);
          setNextKey((k) => k + 1);
        }}
      >
        <Plus className="size-4" /> إضافة نقطة
      </Button>
    </fieldset>
  );
}

function WeekdayPicker({ initial }: { initial: number[] }) {
  const state = useActionFormState();
  const echoed = state.values?.__days;
  const days = new Set(
    echoed !== undefined ? echoed.split(",").filter(Boolean).map(Number) : initial,
  );
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-ink">
        أيام التشغيل (اتركها فارغة لكل الأيام)
      </legend>
      <div className="flex flex-wrap gap-3">
        {WEEKDAY_ORDER.map((d) => (
          <label key={d} className="inline-flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              name="operating_days"
              value={d}
              defaultChecked={days.has(d)}
              className="size-4 accent-forest-700"
            />
            {WEEKDAY_LABELS_AR[d]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function RouteForm({
  action,
  types,
  route,
}: {
  action: (state: FormState, formData: FormData) => Promise<FormState>;
  types: OperationType[];
  route?: Route;
}) {
  const stops = route?.stops ?? [];
  const origin = stops.find((s) => s.kind === "ORIGIN");
  const destination = stops.find((s) => s.kind === "DESTINATION");
  const intermediate = stops.filter((s) => s.kind === "INTERMEDIATE").map(toDraft);
  return (
    <ActionForm
      action={action}
      submitLabel={route ? "حفظ المسار" : "إضافة المسار"}
      version={route?.updated_at}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField
          name="name"
          label="اسم المسار"
          defaultValue={route?.name}
          required
          placeholder="موقف ⇄ جامعة"
        />
        {route ? (
          <div className="space-y-1.5">
            <p className="text-sm font-medium text-ink">نوع التشغيل</p>
            <p className="h-10 py-2 text-sm">{route.operation_type.name_ar}</p>
          </div>
        ) : (
          <SelectField
            name="operation_type_id"
            label="نوع التشغيل"
            options={types
              .filter((t) => t.uses_routes)
              .map((t) => ({ value: t.id, label: t.name_ar }))}
            placeholder="اختر النوع"
            required
          />
        )}
        <SelectField
          name="trip_pattern"
          label="نمط الرحلات"
          defaultValue={route?.trip_pattern ?? "ROUND_TRIP"}
          options={options(TRIP_PATTERN_LABELS_AR)}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <StopFields prefix="origin" title="نقطة البداية" stop={origin} />
        <StopFields prefix="destination" title="نقطة النهاية" stop={destination} />
      </div>
      <IntermediateStops initial={intermediate} />
      <p className="text-xs text-ink-muted">
        الإحداثيات ونصف القطر تُستخدم لاحقًا لاكتشاف الوصول للمحطات وعدّ الدورات تلقائيًا من GPS.
      </p>
      <div className="grid gap-4 sm:grid-cols-4">
        <TextField
          name="expected_distance_km"
          label="المسافة المتوقعة (كم)"
          defaultValue={route?.expected_distance_km}
          inputMode="decimal"
        />
        <TextField
          name="expected_duration_minutes"
          label="المدة المتوقعة (دقيقة)"
          defaultValue={route?.expected_duration_minutes}
          inputMode="numeric"
        />
        <TextField
          name="window_start"
          label="بداية فترة التشغيل"
          type="time"
          defaultValue={route?.window_start?.slice(0, 5)}
        />
        <TextField
          name="window_end"
          label="نهاية فترة التشغيل"
          type="time"
          defaultValue={route?.window_end?.slice(0, 5)}
        />
      </div>
      <WeekdayPicker initial={route?.operating_days ?? []} />
      <TextareaField name="notes" label="ملاحظات" defaultValue={route?.notes} rows={2} />
    </ActionForm>
  );
}
