import type { Metadata } from "next";
import Link from "next/link";
import { saveExpenseAction } from "@/app/(app)/finance/actions";
import { ExpenseForm } from "@/components/finance/expense-form";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { ExpenseCategory } from "@/lib/finance-types";

export const metadata: Metadata = { title: "تسجيل مصروف" };

export default async function NewExpensePage() {
  const me = await requirePermission("expenses:write");
  const [categories, fleet] = await Promise.all([
    api.get<ExpenseCategory[]>("/expense-categories"),
    fleetOptions(),
  ]);
  return (
    <>
      <PageHeader
        title="تسجيل مصروف"
        breadcrumb={<Link href="/finance/expenses">المصروفات</Link>}
      />
      <Card className="max-w-5xl">
        <CardBody>
          <ExpenseForm
            action={saveExpenseAction.bind(null, "create", null)}
            mode="create"
            vehicles={fleet.vehicles}
            drivers={fleet.drivers}
            categories={categories.map((c) => ({ value: c.id, label: c.name_ar }))}
            canApprove={can(me, "expenses:approve")}
          />
        </CardBody>
      </Card>
    </>
  );
}
