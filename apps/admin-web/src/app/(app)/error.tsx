"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <Card>
      <EmptyState
        title="حدث خطأ أثناء تحميل الصفحة"
        description={
          error.digest
            ? `يمكنك المحاولة مرة أخرى. رقم المرجع: ${error.digest}`
            : "يمكنك المحاولة مرة أخرى."
        }
        action={<Button onClick={reset}>إعادة المحاولة</Button>}
      />
    </Card>
  );
}
