import type { Metadata } from "next";
import Link from "next/link";
import { saveStatementAction } from "@/app/(app)/finance/actions";
import { StatementForm } from "@/components/finance/statement-form";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { Platform } from "@/lib/finance-types";

export const metadata: Metadata = { title: "كشف منصة جديد" };

export default async function NewStatementPage() {
  const me = await requirePermission("revenue:write");
  const [platforms, fleet] = await Promise.all([
    api.get<Platform[]>("/ride-hailing/platforms"),
    fleetOptions(),
  ]);
  return (
    <>
      <PageHeader
        title="كشف منصة جديد"
        description="انقل الأرقام كما هي في كشف المنصة للفترة"
        breadcrumb={<Link href="/finance/ride-hailing">النقل الذكي</Link>}
      />
      <Card className="max-w-5xl">
        <CardBody>
          <StatementForm
            action={saveStatementAction.bind(null, "create", null)}
            mode="create"
            platforms={platforms.map((p) => ({ value: p.id, label: p.name }))}
            vehicles={fleet.vehicles}
            drivers={fleet.drivers}
            canApprove={can(me, "revenue:approve")}
          />
        </CardBody>
      </Card>
    </>
  );
}
