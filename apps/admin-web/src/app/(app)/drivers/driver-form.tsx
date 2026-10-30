import { EMPLOYMENT_STATUS_LABELS_AR, options } from "@go-daily/shared";
import { ActionForm } from "@/components/forms/action-form";
import { CheckboxField, SelectField, TextareaField, TextField } from "@/components/forms/fields";
import type { FormState } from "@/lib/forms";
import type { Driver } from "@/lib/types";

export function DriverForm({
  action,
  driver,
}: {
  action: (state: FormState, formData: FormData) => Promise<FormState>;
  driver?: Driver;
}) {
  return (
    <ActionForm
      action={action}
      submitLabel={driver ? "حفظ التعديلات" : "إضافة السائق"}
      version={driver?.updated_at}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <TextField
          name="full_name"
          label="الاسم بالكامل"
          defaultValue={driver?.full_name}
          required
        />
        <TextField
          name="phone"
          label="رقم الهاتف"
          type="tel"
          defaultValue={driver?.phone}
          required
          hint="يستخدم لتسجيل الدخول في تطبيق السائق"
        />
        <TextField
          name="national_id"
          label="الرقم القومي (اختياري)"
          inputMode="numeric"
          autoComplete="off"
          hint={
            driver?.national_id_masked
              ? `المسجل: ${driver.national_id_masked} — اتركه فارغًا للإبقاء عليه`
              : "14 رقمًا، يتم تخزينه مشفرًا"
          }
        />
        <TextField
          name="license_number"
          label="رقم رخصة القيادة"
          defaultValue={driver?.license_number}
        />
        <TextField
          name="license_expiry"
          label="انتهاء رخصة القيادة"
          type="date"
          defaultValue={driver?.license_expiry}
        />
        <SelectField
          name="employment_status"
          label="حالة العمل"
          defaultValue={driver?.employment_status ?? "ACTIVE"}
          options={options(EMPLOYMENT_STATUS_LABELS_AR)}
          required
          hint={
            driver
              ? "الإيقاف أو إنهاء التعاقد يوقف حساب التطبيق، وإنهاء التعاقد ينهي التكليفات المفتوحة"
              : undefined
          }
        />
        <TextField
          name="hire_date"
          label="تاريخ التعيين"
          type="date"
          defaultValue={driver?.hire_date}
        />
        {driver ? (
          <TextField
            name="end_date"
            label="تاريخ انتهاء العمل"
            type="date"
            defaultValue={driver.end_date}
          />
        ) : null}
      </div>
      {driver?.national_id_masked ? (
        <CheckboxField name="clear_national_id" label="حذف الرقم القومي المسجل" />
      ) : null}
      <TextareaField name="notes" label="ملاحظات" defaultValue={driver?.notes} />
    </ActionForm>
  );
}
