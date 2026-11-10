import { addRouteRevenueRateAction } from "@/app/(app)/operations/actions";
import { ActionForm } from "@/components/forms/action-form";
import { SelectField, TextareaField, TextField } from "@/components/forms/fields";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { formatDate } from "@/lib/format";
import { RATE_MODEL_AR, rateText } from "@/lib/revenue-rates";
import type { RouteRevenueRate } from "@/lib/types";

/**
 * Expected collection per loop/leg for a route (U10). Rates are dated
 * versions: adding one closes the previous, so past days keep their rate.
 */
export function RouteRevenueRates({
  routeId,
  rates,
  canWrite,
  roundTrip,
}: {
  routeId: string;
  rates: RouteRevenueRate[];
  canWrite: boolean;
  roundTrip: boolean;
}) {
  const models = (
    roundTrip ? ["PER_LOOP", "PER_LEG", "PASSENGERS_X_FARE"] : ["PER_LEG", "PASSENGERS_X_FARE"]
  ) as (keyof typeof RATE_MODEL_AR)[];
  return (
    <Card>
      <CardHeader
        title="التحصيل المتوقع"
        description="يُستخدم لمقارنة المتوقع من الدورات المكتشفة بالتحصيل المسجل"
      />
      <CardBody className="space-y-4">
        {rates.length === 0 ? (
          <p className="text-sm text-ink-muted">
            لم يُحدد سعر متوقع لهذا المسار؛ تظهر أيامه في التقرير كـ«لا يوجد سعر متوقع».
          </p>
        ) : (
          <ul className="space-y-2 text-sm">
            {rates.map((r) => (
              <li key={r.id} className="border-b border-line pb-2">
                <p className="font-medium">{rateText(r)}</p>
                <p className="text-xs text-ink-muted">
                  من {formatDate(r.effective_from)}
                  {r.effective_to ? ` إلى ${formatDate(r.effective_to)}` : " (ساري)"}
                  {r.notes ? ` · ${r.notes}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
        {canWrite ? (
          <details>
            <summary className="cursor-pointer text-sm font-medium text-forest-700">
              سعر جديد (يبدأ من تاريخ محدد)
            </summary>
            <ActionForm
              action={addRouteRevenueRateAction.bind(null, routeId)}
              submitLabel="حفظ السعر"
              className="mt-3 space-y-3"
            >
              <SelectField
                name="model"
                label="طريقة الحساب"
                defaultValue={models[0]}
                options={models.map((m) => ({ value: m, label: RATE_MODEL_AR[m] }))}
              />
              {roundTrip ? (
                <TextField
                  name="amount_per_loop"
                  label="السعر لكل دورة (ج.م)"
                  inputMode="decimal"
                  hint="لطريقة «لكل دورة» فقط"
                />
              ) : null}
              <TextField
                name="amount_per_leg"
                label="السعر لكل اتجاه (ج.م)"
                inputMode="decimal"
                hint="لطريقة «لكل اتجاه» فقط"
              />
              <TextField
                name="passengers_per_leg"
                label="عدد الركاب المتوقع لكل اتجاه"
                inputMode="numeric"
                hint="تقدير تخطيطي يُدخل يدويًا، ولا يُحسب من GPS"
              />
              <TextField name="fare" label="الأجرة للراكب (ج.م)" inputMode="decimal" />
              <TextField name="effective_from" label="يبدأ من" type="date" required />
              <TextareaField name="notes" label="ملاحظات" rows={2} />
              <p className="text-xs text-ink-muted">
                السعر الحالي يُغلق تلقائيًا في اليوم السابق للتاريخ الجديد، ولا تتغير الأيام
                السابقة.
              </p>
            </ActionForm>
          </details>
        ) : null}
      </CardBody>
    </Card>
  );
}
