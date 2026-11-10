import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";

export default function ForbiddenPage() {
  return (
    <Card>
      <EmptyState
        title="ليس لديك صلاحية لعرض هذه الصفحة"
        description="إذا كنت تحتاج هذه الصلاحية تواصل مع مدير النظام."
        action={<ButtonLink href="/">العودة للوحة التحكم</ButtonLink>}
      />
    </Card>
  );
}
