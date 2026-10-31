import type { Metadata } from "next";
import { LiveFleetMap } from "@/components/map/live-fleet-map";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api } from "@/lib/api";
import { requirePermission } from "@/lib/auth";
import { tileConfig } from "@/lib/map-config";
import type { LivePosition } from "@/lib/types";

export const metadata: Metadata = { title: "الخريطة المباشرة" };

export default async function TrackingPage() {
  await requirePermission("tracking:read");
  const live = await api.get<LivePosition[]>("/tracking/live");
  return (
    <>
      <PageHeader
        title="الخريطة المباشرة"
        description="آخر موقع مستلم لكل مركبة في وردية نشطة. يتم التحديث كل 15 ثانية."
      />
      <Card>
        <CardBody>
          <LiveFleetMap tiles={tileConfig()} initial={live} height={560} />
        </CardBody>
      </Card>
      <p className="mt-3 text-xs text-ink-muted">
        المواقع تُسجل أثناء ورديات العمل فقط. &quot;غير متصل&quot; يعني عدم وصول نقاط من الجهاز
        لأكثر من 10 دقائق ولا يعني بالضرورة وجود مشكلة — راجع سجل الوردية.
      </p>
    </>
  );
}
