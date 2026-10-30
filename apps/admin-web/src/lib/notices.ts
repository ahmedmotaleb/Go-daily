/**
 * Post-action notices carried in the URL (`?notice=code`) for actions that
 * change the page layout, where an inline form message would disappear.
 */
export const NOTICES = {
  created: "تم الحفظ بنجاح.",
  assignment_created: "تم تسجيل التكليف.",
  assignment_ended: "تم إنهاء التكليف. يبقى محفوظًا في سجل التكليفات.",
  account_created: "تم إنشاء حساب تطبيق السائق. يسجل الدخول برقم هاتفه.",
  account_activated: "تم تفعيل حساب التطبيق.",
  account_deactivated: "تم إيقاف حساب التطبيق وإنهاء جلساته.",
  vehicle_activated: "تم تفعيل المركبة.",
  vehicle_deactivated: "تم إيقاف المركبة.",
  start: "بدأت الوردية.",
  end: "انتهت الوردية وتم تحديث قراءة عداد المركبة.",
  cancel: "تم إلغاء الوردية.",
  odometer_correction: "تم تصحيح قراءات العداد وتسجيل السبب.",
  sessions: "بدأ تشغيل جديد.",
  session_ended: "انتهى التشغيل الحالي.",
} as const;

export type NoticeCode = keyof typeof NOTICES;

export function withNotice(path: string, code: NoticeCode): string {
  const [base] = path.split("?");
  return `${base}?notice=${code}`;
}

/** Only allow returning to an internal detail page. */
export function safeReturnPath(value: unknown, fallback: string): string {
  return typeof value === "string" &&
    /^\/(vehicles|drivers|shifts|users)\/[0-9a-f-]{36}$/.test(value)
    ? value
    : fallback;
}
