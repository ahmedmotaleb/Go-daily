import type { Metadata } from "next";
import { ActionForm } from "@/components/forms/action-form";
import { TextareaField, TextField } from "@/components/forms/fields";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { formatDateTime, formatNumber } from "@/lib/format";
import { updatePoliciesAction } from "./actions";

export const metadata: Metadata = { title: "سياسات المراجعة" };

type PolicyValue = {
  key: string;
  group: string;
  title: string;
  unit: string;
  value: number;
  default: number;
  minimum: number;
  maximum: number;
  integer: boolean;
  overridden: boolean;
};

type Policies = {
  version: number;
  values: PolicyValue[];
  history: {
    version: number;
    created_at: string;
    created_by: string | null;
    reason: string;
    changes: Record<string, [number, number]>;
  }[];
};

/** U47: review thresholds, versioned and audited. */
export default async function PoliciesPage() {
  const me = await requirePermission("exceptions:read");
  const data = await api.get<Policies>("/policies");
  const canEdit = can(me, "settings:manage");
  const groups = [...new Set(data.values.map((v) => v.group))];
  const titles = Object.fromEntries(data.values.map((v) => [v.key, v.title]));
  const current = Object.fromEntries(data.values.map((v) => [v.key, v.value]));

  return (
    <>
      <PageHeader
        title="سياسات المراجعة"
        description={`حدود قواعد المراجعة الحالية · الإصدار ${formatNumber(data.version)}`}
      />
      <Alert tone="info" className="mb-6">
        هذه الحدود تحدد متى تظهر حالة «مراجعة مطلوبة»، ولا تغيّر أي سجل. كل تغيير يحفظ نسخة جديدة مع
        السبب واسم من غيّره، وكل حالة تحتفظ بالحدود التي قيّمت بها.
      </Alert>

      {canEdit ? (
        <ActionForm
          action={updatePoliciesAction.bind(null, current)}
          submitLabel="حفظ نسخة جديدة"
          version={String(data.version)}
          className="space-y-6"
        >
          {groups.map((g) => (
            <Card key={g}>
              <CardHeader title={g} />
              <CardBody className="grid gap-4 sm:grid-cols-2">
                {data.values
                  .filter((v) => v.group === g)
                  .map((v) => (
                    <TextField
                      key={v.key}
                      name={v.key}
                      label={`${v.title} (${v.unit})`}
                      defaultValue={v.value}
                      inputMode="decimal"
                      hint={`الافتراضي ${formatNumber(v.default)} · المسموح ${formatNumber(v.minimum)}–${formatNumber(v.maximum)}${v.overridden ? " · معدّل" : ""}`}
                    />
                  ))}
              </CardBody>
            </Card>
          ))}
          <Card>
            <CardBody>
              <TextareaField
                name="reason"
                label="سبب التغيير"
                required
                rows={2}
                hint="يظهر في السجل. اترك أي حقل فارغًا للرجوع إلى القيمة الافتراضية."
              />
            </CardBody>
          </Card>
        </ActionForm>
      ) : (
        <Card>
          <Table>
            <THead>
              <TR>
                <TH>القاعدة</TH>
                <TH>القيمة</TH>
                <TH>الافتراضي</TH>
              </TR>
            </THead>
            <tbody>
              {data.values.map((v) => (
                <TR key={v.key}>
                  <TD>
                    {v.title} <span className="text-xs text-ink-muted">· {v.group}</span>
                  </TD>
                  <TD className="ltr-nums">
                    {formatNumber(v.value)} {v.unit}{" "}
                    {v.overridden ? <Badge tone="info">معدّل</Badge> : null}
                  </TD>
                  <TD className="ltr-nums">{formatNumber(v.default)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      <Card className="mt-6">
        <CardHeader title="سجل الإصدارات" />
        {data.history.length === 0 ? (
          <p className="px-5 py-4 text-sm text-ink-muted">
            لم تُغيّر السياسة بعد؛ كل القيم هي الافتراضية.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {data.history.map((h) => (
              <li key={h.version} className="space-y-1 px-5 py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">الإصدار {formatNumber(h.version)}</Badge>
                  <span className="ltr-nums text-ink-soft">{formatDateTime(h.created_at)}</span>
                  {h.created_by ? <span className="text-ink-soft">· {h.created_by}</span> : null}
                </div>
                <p>{h.reason}</p>
                <ul className="text-xs text-ink-soft">
                  {Object.entries(h.changes).map(([k, [from, to]]) => (
                    <li key={k}>
                      {titles[k] ?? k}: <span className="ltr-nums">{formatNumber(from)}</span> ←{" "}
                      <span className="ltr-nums">{formatNumber(to)}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
