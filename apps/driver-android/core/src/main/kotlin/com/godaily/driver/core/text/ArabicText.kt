package com.godaily.driver.core.text

import com.godaily.driver.core.tracking.TrackingIssue
import com.godaily.driver.core.tracking.TrackingLevel

/** Driver-facing Arabic copy for tracking states. Plain, short, no blame. */
object ArabicText {
    /** Short headline: the same words in the app, the notification and the pilot test plan. */
    fun level(level: TrackingLevel): String = when (level) {
        TrackingLevel.IDLE -> "الوردية منتهية"
        TrackingLevel.ACTIVE -> "التتبع يعمل"
        TrackingLevel.UPLOADING -> "جاري رفع المواقع"
        TrackingLevel.OFFLINE_RECORDING -> "تسجيل بدون إنترنت"
        TrackingLevel.WEAK_SIGNAL -> "إشارة الموقع ضعيفة"
        TrackingLevel.LOCATION_OFF -> "الموقع غير متاح"
        TrackingLevel.PERMISSION_REQUIRED -> "صلاحية الموقع مطلوبة"
        TrackingLevel.STOPPED -> "التتبع متوقف"
    }

    /** One sentence under the headline saying what is happening and what to do. */
    fun detail(level: TrackingLevel): String = when (level) {
        TrackingLevel.IDLE -> "لا يُجمع الموقع خارج الوردية."
        TrackingLevel.ACTIVE -> "يُسجَّل موقع الوردية ويُرسل تلقائيًا."
        TrackingLevel.UPLOADING -> "عاد الاتصال، ويتم إرسال المواقع المحفوظة على الهاتف."
        TrackingLevel.OFFLINE_RECORDING -> "لا يوجد إنترنت. يُسجَّل الموقع على الهاتف ويُرسل عند عودة الاتصال."
        TrackingLevel.WEAK_SIGNAL -> "لا توجد قراءات موقع حديثة. قد تكون في مكان مغلق أو الإشارة ضعيفة."
        TrackingLevel.LOCATION_OFF -> "خدمة الموقع في الهاتف مغلقة. افتحها لاستمرار التتبع."
        TrackingLevel.PERMISSION_REQUIRED -> "اسمح للتطبيق بالوصول إلى الموقع لاستمرار تتبع الوردية."
        TrackingLevel.STOPPED -> "توجد وردية نشطة لكن التتبع لا يعمل. أعد تشغيله."
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
