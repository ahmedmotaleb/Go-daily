/** Client-safe form state shared by server actions and form components. */
export type FormState = {
  ok?: boolean;
  message?: string;
  fieldErrors?: Record<string, string>;
  /** Echo submitted values so the form keeps them after a failed submit. */
  values?: Record<string, string>;
};

export const initialFormState: FormState = {};

/**
 * React resets uncontrolled forms after an action completes. Keying the form
 * on the submitted values remounts it with those values as defaults, so a
 * failed submit never silently reverts a field (e.g. a <select>) to its
 * first option.
 */
export function formKey(state: FormState, version?: string): string {
  return `${version ?? ""}|${JSON.stringify(state.values ?? {})}`;
}
