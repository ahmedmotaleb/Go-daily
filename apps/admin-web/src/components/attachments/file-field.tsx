"use client";

import { FieldError } from "@/components/forms/fields";

export function FileField() {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="file" className="text-sm font-medium text-ink">
        ملف (صورة JPG/PNG/WebP أو PDF، حتى 10 ميجابايت)
      </label>
      <input
        id="file"
        name="file"
        type="file"
        accept="image/jpeg,image/png,image/webp,application/pdf"
        capture="environment"
        className="block w-full text-sm file:me-3 file:rounded-[var(--radius-control)] file:border-0 file:bg-forest-50 file:px-3 file:py-2 file:text-forest-800"
      />
      <FieldError name="file" />
    </div>
  );
}
