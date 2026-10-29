import type { Metadata } from "next";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { getCurrentUser } from "@/lib/auth";

export const metadata: Metadata = { title: "لوحة التحكم" };

export default async function DashboardPage() {
  const user = await getCurrentUser();
  return (
    <>
      <PageHeader title="لوحة التحكم" description={`مرحبًا ${user.full_name}`} />
      <Card>
        <CardBody>
          <p className="text-ink-muted">
            سيتم عرض مؤشرات التشغيل هنا بعد تفعيل وحدات الأسطول والورديات.
          </p>
        </CardBody>
      </Card>
    </>
  );
}
