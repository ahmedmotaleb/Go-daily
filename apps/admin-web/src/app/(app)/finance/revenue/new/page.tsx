import type { Metadata } from "next";
import Link from "next/link";
import { saveRevenueAction } from "@/app/(app)/finance/actions";
import { RevenueForm } from "@/components/finance/revenue-form";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { OperationType } from "@/lib/types";

export const metadata: Metadata = { title: "تسجيل إيراد" };

export default async function NewRevenuePage() {
  const me = await requirePermission("revenue:write");
  const [types, fleet] = await Promise.all([
    api.get<OperationType[]>("/operation-types"),
    fleetOptions(),
  ]);
  return (
    <>
      <PageHeader title="تسجيل إيراد" breadcrumb={<Link href="/finance/revenue">الإيرادات</Link>} />
      <Card className="max-w-5xl">
        <CardBody>
          <RevenueForm
            action={saveRevenueAction.bind(null, "create", null)}
            mode="create"
            vehicles={fleet.vehicles}
            drivers={fleet.drivers}
            operationTypes={types.map((t) => ({ value: t.id, label: t.name_ar }))}
            canApprove={can(me, "revenue:approve")}
          />
        </CardBody>
      </Card>
    </>
  );
}
