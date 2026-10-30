import type { Metadata } from "next";
import Link from "next/link";
import { saveExpenseAction } from "@/app/(app)/finance/actions";
import { ExpenseForm } from "@/components/finance/expense-form";
import { DetailRow } from "@/components/finance/filters";
import { ReviewPanel } from "@/components/finance/review";
import { Notice } from "@/components/notice";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { EXPENSE_GROUP_LABELS, PAID_BY_LABELS, PAYMENT_METHOD_LABELS } from "@/lib/finance-labels";
import { fleetOptions } from "@/lib/finance-refs";
import type { Expense, ExpenseCategory } from "@/lib/finance-types";
import { formatDateTime, formatMoney } from "@/lib/format";

export const metadata: Metadata = { title: "مصروف" };

export default async function ExpenseDetailPage({
  params,
  searchParams,
}: PageProps<"/finance/expenses/[id]">) {
  const me = await requirePermission("expenses:read");
  const { id } = await params;
  const { notice } = await searchParams;
  const e = await api.get<Expense>(`/expenses/${id}`);
  const canEdit =
    can(me, "expenses:write") && (e.status === "SUBMITTED" || e.status === "REJECTED");
  const canReview = can(me, "expenses:approve");
  const needsForm = canEdit || (canReview && e.status === "APPROVED");
  const [categories, fleet] = needsForm
    ? await Promise.all([api.get<ExpenseCategory[]>("/expense-categories"), fleetOptions()])
    : [[], { vehicles: [], drivers: [] }];
  const categoryOptions = categories.map((c) => ({ value: c.id, label: c.name_ar }));

  return (
    <>
      <PageHeader
        title={`${e.category.name_ar} — ${e.vehicle.name}`}
        description={formatDateTime(e.occurred_at)}
        breadcrumb={<Link href="/finance/expenses">المصروفات</Link>}
      />
      <Notice code={notice} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="التفاصيل" />
          <CardBody>
            <dl className="divide-y divide-line">
              <DetailRow label="المركبة">
                <Link href={`/vehicles/${e.vehicle.id}`} className="ltr-nums hover:underline">
                  {e.vehicle.name}
                </Link>
              </DetailRow>
              <DetailRow label="السائق">{e.driver?.name ?? "—"}</DetailRow>
              <DetailRow label="التصنيف">
                {e.category.name_ar} ({EXPENSE_GROUP_LABELS[e.category.pnl_group]})
              </DetailRow>
              <DetailRow label="المبلغ">
                <span className="ltr-nums text-base font-bold">{formatMoney(e.amount)}</span>
              </DetailRow>
              <DetailRow label="المورد / الجهة">{e.vendor ?? "—"}</DetailRow>
              <DetailRow label="الدفع">
                {PAYMENT_METHOD_LABELS[e.payment_method]} · {PAID_BY_LABELS[e.paid_by]}
              </DetailRow>
              {e.notes ? <DetailRow label="ملاحظات">{e.notes}</DetailRow> : null}
            </dl>
          </CardBody>
        </Card>
        <ReviewPanel resource="expenses" record={e} canReview={canReview} />
      </div>
      {canEdit ? (
        <Card className="mt-6">
          <CardHeader title="تعديل المصروف" description="التعديل متاح قبل الاعتماد فقط" />
          <CardBody>
            <ExpenseForm
              action={saveExpenseAction.bind(null, "edit", e.id)}
              mode="edit"
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              categories={categoryOptions}
              record={e}
              canApprove={false}
            />
          </CardBody>
        </Card>
      ) : null}
      {canReview && e.status === "APPROVED" ? (
        <Card className="mt-6">
          <CardHeader
            title="تصحيح مصروف معتمد"
            description="يُلغى هذا السجل وينشأ سجل جديد مرتبط به؛ يبقى الاثنان في السجل"
          />
          <CardBody>
            <ExpenseForm
              action={saveExpenseAction.bind(null, "correct", e.id)}
              mode="correct"
              vehicles={fleet.vehicles}
              drivers={fleet.drivers}
              categories={categoryOptions}
              record={e}
              canApprove
            />
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
