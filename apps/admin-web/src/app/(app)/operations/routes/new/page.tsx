import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import type { OperationType } from "@/lib/types";
import { createRouteAction } from "../../actions";
import { RouteForm } from "../route-form";

export const metadata: Metadata = { title: "مسار جديد" };

export default async function NewRoutePage() {
  await requirePermission("operations:write");
  const types = await api.get<OperationType[]>("/operation-types");
  return (
    <>
      <PageHeader title="مسار جديد" breadcrumb={<Link href="/operations">التشغيل</Link>} />
      <Card>
        <CardBody>
          <RouteForm action={createRouteAction} types={types} />
        </CardBody>
      </Card>
    </>
  );
}
