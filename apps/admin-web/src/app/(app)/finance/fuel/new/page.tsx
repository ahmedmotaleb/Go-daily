import type { Metadata } from "next";
import Link from "next/link";
import { saveFuelAction } from "@/app/(app)/finance/actions";
import { FuelForm } from "@/components/finance/fuel-form";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { FuelType } from "@/lib/finance-types";

export const metadata: Metadata = { title: "تسجيل وقود" };

export default async function NewFuelPage() {
  const me = await requirePermission("fuel:write");
  const [types, fleet] = await Promise.all([api.get<FuelType[]>("/fuel-types"), fleetOptions()]);
  return (
    <>
      <PageHeader
        title="تسجيل وقود أو زيت"
        breadcrumb={<Link href="/finance/fuel">الوقود والزيوت</Link>}
      />
      <Card className="max-w-5xl">
        <CardBody>
          <FuelForm
            action={saveFuelAction.bind(null, "create", null)}
            mode="create"
            vehicles={fleet.vehicles}
            drivers={fleet.drivers}
            fuelTypes={types.map((t) => ({ value: t.id, label: t.name_ar }))}
            canApprove={can(me, "expenses:approve")}
          />
        </CardBody>
      </Card>
    </>
  );
}
