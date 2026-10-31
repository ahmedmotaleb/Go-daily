package com.godaily.driver.core.text

import com.godaily.driver.core.tracking.TrackingIssue
import com.godaily.driver.core.tracking.TrackingLevel

/** Driver-facing Arabic copy for tracking states. Plain, short, no blame. */
object ArabicText {
    fun level(level: TrackingLevel): String = when (level) {
        TrackingLevel.IDLE -> "التتبع متوقف — لا توجد وردية نشطة"
        TrackingLevel.ACTIVE -> "تتبع الوردية يعمل"
        TrackingLevel.OFFLINE_RECORDING -> "لا يوجد إنترنت — يتم تسجيل الموقع وسيُرسل عند عودة الاتصال"
        TrackingLevel.WEAK_SIGNAL -> "إشارة الموقع ضعيفة — لا توجد قراءات حديثة"
        TrackingLevel.BLOCKED -> "التتبع متوقف — الموقع غير متاح للتطبيق"
        TrackingLevel.STOPPED -> "التتبع متوقف — اضغط لإعادة تشغيله"
    }

    fun issue(issue: TrackingIssue): String = when (issue) {
        TrackingIssue.LOCATION_PERMISSION_DENIED -> "إذن الموقع مرفوض. فعّله من الإعدادات لاستمرار تتبع الوردية."
        TrackingIssue.LOCATION_DISABLED -> "خدمة الموقع في الهاتف مغلقة. افتحها لاستمرار التتبع."
        TrackingIssue.SERVICE_NOT_RUNNING -> "خدمة التتبع لا تعمل رغم وجود وردية نشطة."
        TrackingIssue.NO_RECENT_FIX -> "لم يصل موقع حديث. قد تكون في مكان مغلق أو الإشارة ضعيفة."
        TrackingIssue.OFFLINE -> "لا يوجد اتصال بالإنترنت. النقاط محفوظة على الهاتف."
        TrackingIssue.SYNC_BACKLOG -> "توجد نقاط كثيرة بانتظار الإرسال."
        TrackingIssue.BACKGROUND_PERMISSION_MISSING ->
            "اختر «السماح طوال الوقت» حتى يستأنف التتبع تلقائيًا بعد إعادة تشغيل الهاتف."
        TrackingIssue.BATTERY_OPTIMIZED ->
            "تحسين البطارية مفعّل للتطبيق وقد يوقف التتبع. استثنِ التطبيق من تحسين البطارية."
        TrackingIssue.NOTIFICATIONS_BLOCKED -> "الإشعارات مغلقة، فلن يظهر إشعار التتبع أثناء الوردية."
    }

    fun pending(count: Int): String = when {
        count <= 0 -> "كل النقاط مُرسلة"
        count == 1 -> "نقطة واحدة بانتظار الإرسال"
        count == 2 -> "نقطتان بانتظار الإرسال"
        count in 3..10 -> "$count نقاط بانتظار الإرسال"
        else -> "$count نقطة بانتظار الإرسال"
    }
}
