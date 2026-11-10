import type { Metadata } from "next";
import Link from "next/link";
import { operationOptions } from "@/components/domain/operation-select";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { formatNumber } from "@/lib/format";
import type { Driver, OperationType, Page, Route, Vehicle } from "@/lib/types";
import { createShiftAction } from "../actions";
import { ShiftForm } from "./shift-form";

export const metadata: Metadata = { title: "وردية جديدة" };

export default async function NewShiftPage() {
  await requirePermission("shifts:write");
  const [drivers, vehicles, types, routes] = await Promise.all([
    api.get<Page<Driver>>("/drivers", { employment_status: "ACTIVE", page_size: 100 }),
    api.get<Page<Vehicle>>("/vehicles", { is_active: true, page_size: 100 }),
    api.get<OperationType[]>("/operation-types"),
    api.get<Page<Route>>("/routes", { is_active: true, page_size: 100 }),
  ]);
  const driverOptions = drivers.items.map((d) => ({
    value: d.id,
    label: d.current_assignments.length
      ? `${d.full_name} — ${d.current_assignments.map((a) => a.vehicle_code).join("، ")}`
      : d.full_name,
  }));
  const vehicleOptions = vehicles.items.map((v) => ({
    value: v.id,
    label: `${v.internal_code} · ${v.plate_number} (آخر عداد: ${formatNumber(v.current_odometer_km)})`,
  }));
  return (
    <>
      <PageHeader title="وردية جديدة" breadcrumb={<Link href="/shifts">الورديات</Link>} />
      <Card className="max-w-4xl">
        <CardBody>
          <ShiftForm
            action={createShiftAction}
            drivers={driverOptions}
            vehicles={vehicleOptions}
            operations={operationOptions(types, routes.items)}
          />
        </CardBody>
      </Card>
    </>
  );
}
