import type { Metadata } from "next";
import Link from "next/link";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { requirePermission } from "@/lib/auth";
import { createDriverAction } from "../actions";
import { DriverForm } from "../driver-form";

export const metadata: Metadata = { title: "سائق جديد" };

export default async function NewDriverPage() {
  await requirePermission("drivers:write");
  return (
    <>
      <PageHeader title="سائق جديد" breadcrumb={<Link href="/drivers">السائقون</Link>} />
      <Card>
        <CardBody>
          <DriverForm action={createDriverAction} />
        </CardBody>
      </Card>
    </>
  );
}
