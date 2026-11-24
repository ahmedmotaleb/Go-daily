package com.godaily.driver.core.tracking

/** One requirement on the "حالة التتبع" screen (design: متطلبات التتبع). */
enum class CheckKind { LOCATION_PERMISSION, PHONE_GPS, BATTERY, INTERNET, NOTIFICATIONS }

enum class CheckState {
    OK,
    /** Works, but something should be fixed (e.g. "while using the app" only, or offline). */
    WARNING,
    /** Tracking cannot work until this is fixed. */
    PROBLEM,
    /** Not checked outside a shift: shown as "checked when the shift starts", never as OK. */
    NOT_CHECKED,
}

data class TrackingCheck(val kind: CheckKind, val state: CheckState, val issue: TrackingIssue?)

/**
 * The requirement list derived from a [TrackingStatus]. Outside a shift the
 * phone is not inspected (only the upload queue is), so every requirement
 * reads NOT_CHECKED instead of pretending everything is fine.
 */
fun trackingChecks(status: TrackingStatus?): List<TrackingCheck> {
    val inShift = status != null && status.level != TrackingLevel.IDLE
    val issues = status?.issues.orEmpty()
    fun check(kind: CheckKind, problem: TrackingIssue?, warning: TrackingIssue?): TrackingCheck = when {
        !inShift -> TrackingCheck(kind, CheckState.NOT_CHECKED, null)
        problem != null && problem in issues -> TrackingCheck(kind, CheckState.PROBLEM, problem)
        warning != null && warning in issues -> TrackingCheck(kind, CheckState.WARNING, warning)
        else -> TrackingCheck(kind, CheckState.OK, null)
    }
    return listOf(
        check(
            CheckKind.LOCATION_PERMISSION,
            TrackingIssue.LOCATION_PERMISSION_DENIED,
            TrackingIssue.BACKGROUND_PERMISSION_MISSING,
        ),
        check(CheckKind.PHONE_GPS, TrackingIssue.LOCATION_DISABLED, TrackingIssue.NO_RECENT_FIX),
        check(CheckKind.BATTERY, null, TrackingIssue.BATTERY_OPTIMIZED),
        check(CheckKind.INTERNET, null, TrackingIssue.OFFLINE),
        check(CheckKind.NOTIFICATIONS, null, TrackingIssue.NOTIFICATIONS_BLOCKED),
    )
}
