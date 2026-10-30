import { Card, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Page } from "@/lib/types";

type AuditEntry = {
  id: string;
  occurred_at: string;
  actor_user_id: string | null;
  actor_role: string | null;
  action: string;
  changes: Record<string, { old?: unknown; new?: unknown; changed?: boolean }> | null;
  reason: string | null;
};

const ACTION_LABELS: Record<string, string> = {
  "user.created": "إنشاء الحساب",
  "user.updated": "تعديل البيانات",
  "user.activated": "تفعيل الحساب",
  "user.deactivated": "إيقاف الحساب",
  "user.password_reset": "تعيين كلمة مرور جديدة",
  "auth.login.success": "تسجيل دخول",
  "auth.login.failed": "محاولة دخول فاشلة",
  "auth.logout": "تسجيل خروج",
  "auth.password_changed": "تغيير كلمة المرور",
  "vehicle.created": "إضافة المركبة",
  "vehicle.updated": "تعديل بيانات المركبة",
  "vehicle.activated": "تفعيل المركبة",
  "vehicle.deactivated": "إيقاف المركبة",
  "driver.created": "إضافة السائق",
  "driver.updated": "تعديل بيانات السائق",
  "driver.sensitive_viewed": "عرض الرقم القومي",
  "driver.app_account_created": "إنشاء حساب التطبيق",
};

/** Arabic names for audited fields; unknown fields fall back to their key. */
const FIELD_LABELS: Record<string, string> = {
  full_name: "الاسم",
  phone: "رقم الهاتف",
  email: "البريد الإلكتروني",
  role: "الصلاحية",
  is_active: "حالة التفعيل",
  notes: "ملاحظات",
  internal_code: "الكود الداخلي",
  plate_number: "رقم اللوحة",
  vehicle_type_id: "نوع المركبة",
  manufacturer: "الشركة المصنعة",
  model: "الموديل",
  model_year: "سنة الصنع",
  color: "اللون",
  ownership_status: "الملكية",
  current_odometer_km: "قراءة العداد",
  license_expiry: "انتهاء الرخصة",
  insurance_expiry: "انتهاء التأمين",
  national_id: "الرقم القومي",
  license_number: "رقم الرخصة",
  employment_status: "حالة العمل",
  hire_date: "تاريخ التعيين",
  end_date: "تاريخ انتهاء العمل",
};

function describeChanges(changes: AuditEntry["changes"]): string | null {
  if (!changes) return null;
  return Object.keys(changes)
    .map((k) => FIELD_LABELS[k] ?? k)
    .join("، ");
}

/** Read-only history of changes for one record. */
export async function AuditTrail({
  entityType,
  entityId,
  title = "سجل التغييرات",
}: {
  entityType: string;
  entityId: string;
  title?: string;
}) {
  const data = await api.get<Page<AuditEntry>>("/audit-logs", {
    entity_type: entityType,
    entity_id: entityId,
    page_size: 15,
  });
  return (
    <Card>
      <CardHeader title={title} />
      {data.items.length === 0 ? (
        <p className="px-5 py-4 text-sm text-ink-muted">لا توجد سجلات.</p>
      ) : (
        <ol className="divide-y divide-line">
          {data.items.map((e) => (
            <li key={e.id} className="px-5 py-3 text-sm">
              <p className="font-medium text-ink">{ACTION_LABELS[e.action] ?? e.action}</p>
              <p className="text-xs text-ink-muted">{formatDateTime(e.occurred_at)}</p>
              {describeChanges(e.changes) ? (
                <p className="mt-1 text-xs text-ink-muted">الحقول: {describeChanges(e.changes)}</p>
              ) : null}
              {e.reason ? <p className="mt-1 text-xs text-ink">السبب: {e.reason}</p> : null}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
