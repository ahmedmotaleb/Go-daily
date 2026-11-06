import type { Metadata } from "next";
import Link from "next/link";
import { saveMaintenanceAction } from "@/app/(app)/finance/actions";
import { MaintenanceForm } from "@/components/maintenance/maintenance-form";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { fleetOptions } from "@/lib/finance-refs";
import type { MaintenanceType } from "@/lib/maintenance-types";
import { spUuid } from "@/lib/search";

export const metadata: Metadata = { title: "تسجيل صيانة" };

export default async function NewMaintenancePage({
  searchParams,
}: PageProps<"/maintenance/records/new">) {
  const me = await requirePermission("maintenance:write");
  const sp = await searchParams;
  const [types, fleet] = await Promise.all([
    api.get<MaintenanceType[]>("/maintenance/types"),
    fleetOptions(),
  ]);
  return (
    <>
      <PageHeader title="تسجيل صيانة منفذة" breadcrumb={<Link href="/maintenance">الصيانة</Link>} />
      <Card className="max-w-5xl">
        <CardBody>
          <MaintenanceForm
            action={saveMaintenanceAction.bind(null, "create", null)}
            mode="create"
            vehicles={fleet.vehicles}
            types={types.map((t) => ({ value: t.id, label: t.name_ar }))}
            canApprove={can(me, "expenses:approve")}
            defaultVehicleId={spUuid(sp, "vehicle_id")}
          />
        </CardBody>
      </Card>
    </>
  );
}
