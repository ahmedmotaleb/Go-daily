package com.godaily.driver.core.text

import com.godaily.driver.core.tracking.CheckKind
import com.godaily.driver.core.tracking.CheckState
import com.godaily.driver.core.tracking.TrackingCheck
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

    fun checkTitle(kind: CheckKind): String = when (kind) {
        CheckKind.LOCATION_PERMISSION -> "إذن الموقع"
        CheckKind.PHONE_GPS -> "GPS الهاتف"
        CheckKind.BATTERY -> "توفير البطارية"
        CheckKind.INTERNET -> "الإنترنت"
        CheckKind.NOTIFICATIONS -> "إشعار التتبع"
    }

    /** The line under each requirement: what the phone reports now. */
    fun checkState(check: TrackingCheck): String = when (check.state) {
        CheckState.NOT_CHECKED -> "يُفحص عند بدء الوردية"
        CheckState.OK -> when (check.kind) {
            CheckKind.LOCATION_PERMISSION -> "مسموح طوال الوقت"
            CheckKind.PHONE_GPS -> "مفعّل ويصل الموقع"
            CheckKind.BATTERY -> "التطبيق مستثنى"
            CheckKind.INTERNET -> "متصل"
            CheckKind.NOTIFICATIONS -> "ظاهر أثناء الوردية"
        }
        CheckState.WARNING, CheckState.PROBLEM -> when (check.issue) {
            TrackingIssue.LOCATION_PERMISSION_DENIED -> "مرفوض — التتبع لا يعمل"
            TrackingIssue.BACKGROUND_PERMISSION_MISSING -> "أثناء استخدام التطبيق فقط"
            TrackingIssue.LOCATION_DISABLED -> "مغلق — التتبع لا يعمل"
            TrackingIssue.NO_RECENT_FIX -> "لا يصل موقع حديث"
            TrackingIssue.BATTERY_OPTIMIZED -> "مفعّل للتطبيق وقد يوقف التتبع"
            TrackingIssue.OFFLINE -> "غير متصل الآن — المواقع محفوظة على الهاتف"
            TrackingIssue.NOTIFICATIONS_BLOCKED -> "الإشعارات مغلقة"
            TrackingIssue.SERVICE_NOT_RUNNING, TrackingIssue.SYNC_BACKLOG, null -> "يحتاج مراجعة"
        }
    }

    /** "الآن" / "منذ 8 ث" / "منذ 4 د" / "منذ 2 س" for an age in seconds. */
    fun since(seconds: Long): String = when {
        seconds < 10 -> "الآن"
        seconds < 60 -> "منذ $seconds ث"
        seconds < 3_600 -> "منذ ${seconds / 60} د"
        else -> "منذ ${seconds / 3_600} س"
    }

    /** Morning / evening greeting by local hour (0-23). */
    fun greeting(hour: Int, name: String?): String {
        val first = name?.trim()?.split(' ')?.firstOrNull()?.takeIf { it.isNotEmpty() }
        val word = if (hour in 4..11) "صباح الخير" else "مساء الخير"
        return if (first != null) "$word، $first" else word
    }

    fun pending(count: Int): String = when {
        count <= 0 -> "كل النقاط مُرسلة"
        count == 1 -> "نقطة واحدة بانتظار الإرسال"
        count == 2 -> "نقطتان بانتظار الإرسال"
        count in 3..10 -> "$count نقاط بانتظار الإرسال"
        else -> "$count نقطة بانتظار الإرسال"
    }
}
