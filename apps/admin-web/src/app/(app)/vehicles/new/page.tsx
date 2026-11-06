import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import type { VehicleType } from "@/lib/types";
import { createVehicleAction } from "../actions";
import { VehicleForm } from "../vehicle-form";

export const metadata: Metadata = { title: "مركبة جديدة" };

export default async function NewVehiclePage() {
  await requirePermission("vehicles:write");
  const types = await api.get<VehicleType[]>("/vehicle-types");
  return (
    <>
      <PageHeader title="مركبة جديدة" breadcrumb={<Link href="/vehicles">الأسطول</Link>} />
      <Card>
        <CardBody>
          <VehicleForm action={createVehicleAction} types={types} />
        </CardBody>
      </Card>
    </>
  );
}
