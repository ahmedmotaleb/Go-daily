import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { PlausibilityCheck } from "@/lib/finance-types";
import { CHECK_AR, checkExplanation, coveredNote, RESULT_AR } from "@/lib/fuel-plausibility";

/** Plausibility of one purchase (U15): every check with its result; missing data is said so. */
export function FuelPlausibility({ checks }: { checks: PlausibilityCheck[] }) {
  return (
    <Card className="mt-6">
      <CardHeader
        title="فحوص المعقولية"
        description="مقارنة السجل بالإسناد والورديات والعداد وGPS والسجلات السابقة. النتيجة سبب للمراجعة وليست حكمًا."
      />
      <CardBody>
        <ul className="divide-y divide-line text-sm">
          {checks.map((c) => {
            const why = checkExplanation(c);
            const covered = coveredNote(c);
            return (
              <li key={c.code} className="flex flex-wrap items-start justify-between gap-2 py-2">
                <div>
                  <p className="font-medium">{CHECK_AR[c.code]}</p>
                  {why ? <p className="text-xs text-ink-muted">{why}</p> : null}
                  {covered ? <p className="text-xs text-ink-muted">{covered}</p> : null}
                </div>
                <Badge tone={RESULT_AR[c.result].tone}>{RESULT_AR[c.result].label}</Badge>
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}
