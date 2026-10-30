"use client";

import type { ComponentProps } from "react";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/field";
import { useActionFormState } from "./action-form";

type Base = {
  name: string;
  label: string;
  hint?: string;
  required?: boolean;
  className?: string;
};

function useField(name: string, defaultValue?: string | number | null) {
  const state = useActionFormState();
  const echoed = state.values?.[name];
  return {
    error: state.fieldErrors?.[name],
    value:
      echoed ??
      (defaultValue === null || defaultValue === undefined ? undefined : String(defaultValue)),
  };
}

export function TextField({
  name,
  label,
  hint,
  required,
  className,
  defaultValue,
  ...input
}: Base & { defaultValue?: string | number | null } & Omit<
    ComponentProps<"input">,
    "name" | "defaultValue"
  >) {
  const { error, value } = useField(name, defaultValue);
  return (
    <Field
      label={label}
      htmlFor={name}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <Input
        id={name}
        name={name}
        defaultValue={value}
        invalid={!!error}
        required={required}
        {...input}
      />
    </Field>
  );
}

export function SelectField({
  name,
  label,
  hint,
  required,
  className,
  defaultValue,
  options,
  placeholder,
}: Base & {
  defaultValue?: string | null;
  options: { value: string; label: string }[];
  placeholder?: string;
}) {
  const { error, value } = useField(name, defaultValue);
  return (
    <Field
      label={label}
      htmlFor={name}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <Select
        id={name}
        name={name}
        defaultValue={value ?? ""}
        invalid={!!error}
        required={required}
      >
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    </Field>
  );
}

export function TextareaField({
  name,
  label,
  hint,
  required,
  className,
  defaultValue,
  rows = 3,
}: Base & { defaultValue?: string | null; rows?: number }) {
  const { error, value } = useField(name, defaultValue);
  return (
    <Field
      label={label}
      htmlFor={name}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <Textarea
        id={name}
        name={name}
        defaultValue={value}
        invalid={!!error}
        rows={rows}
        required={required}
      />
    </Field>
  );
}

export function CheckboxField({
  name,
  label,
  defaultChecked,
}: {
  name: string;
  label: string;
  defaultChecked?: boolean;
}) {
  const state = useActionFormState();
  const checked = state.values ? state.values[name] === "on" : defaultChecked;
  return <Checkbox name={name} label={label} defaultChecked={checked} />;
}

/** Shows a form-level error for a field that has no input (e.g. a hidden id). */
export function FieldError({ name }: { name: string }) {
  const error = useActionFormState().fieldErrors?.[name];
  return error ? (
    <p className="text-xs text-danger" role="alert">
      {error}
    </p>
  ) : null;
}
