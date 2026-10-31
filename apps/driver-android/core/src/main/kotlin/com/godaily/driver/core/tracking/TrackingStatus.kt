package com.godaily.driver.core.tracking

import com.godaily.driver.core.api.TrackingEventType

/** Everything the app knows about tracking health at one moment. */
data class TrackingSignals(
    val hasActiveShift: Boolean,
    /** Precise location granted (at least while the app is in use). */
    val locationPermission: Boolean,
    /** "Allow all the time": needed to resume tracking after a reboot. */
    val backgroundPermission: Boolean,
    /** Android 13+: the tracking notification can be shown. */
    val notificationsAllowed: Boolean,
    /** System-wide location switch. */
    val locationEnabled: Boolean,
    val serviceRunning: Boolean,
    /** When the tracking service last (re)started; null when not running. */
    val trackingSinceMillis: Long?,
    val lastFixAtMillis: Long?,
    val nowMillis: Long,
    val online: Boolean,
    val pendingPoints: Int,
    val oldestPendingAtMillis: Long?,
    val batteryOptimizationExempt: Boolean,
    val expectedIntervalMillis: Long,
)

/** The headline state shown to the driver (and mirrored in the notification). */
enum class TrackingLevel {
    /** No active shift: location is not collected. */
    IDLE,

    /** Recording and uploading normally. */
    ACTIVE,

    /** Recording, but no internet: points are queued on the phone. */
    OFFLINE_RECORDING,

    /** Service running but no recent location fix (tunnel, indoors, weak GPS). */
    WEAK_SIGNAL,

    /** Cannot record: permission revoked or system location switched off. */
    BLOCKED,

    /** Shift is active but the tracking service is not running. */
    STOPPED,
}

enum class TrackingIssue {
    LOCATION_PERMISSION_DENIED,
    LOCATION_DISABLED,
    SERVICE_NOT_RUNNING,
    NO_RECENT_FIX,
    OFFLINE,
    SYNC_BACKLOG,
    BACKGROUND_PERMISSION_MISSING,
    BATTERY_OPTIMIZED,
    NOTIFICATIONS_BLOCKED,
}

data class TrackingStatus(
    val level: TrackingLevel,
    val issues: Set<TrackingIssue>,
    val pendingPoints: Int,
    val lastFixAtMillis: Long?,
)

data class StatusParams(
    /** Minimum silence before "no recent fix" (first fixes can take a while). */
    val minNoFixMillis: Long = 120_000,
    /** Backlog warning: points waiting longer than this while online... */
    val backlogAgeMillis: Long = 10 * 60_000,
    /** ...or more points than this waiting at all. */
    val backlogPoints: Int = 2_000,
)

/** Derives the driver-visible status. Pure: same signals, same status. */
fun evaluateTracking(s: TrackingSignals, params: StatusParams = StatusParams()): TrackingStatus {
    val issues = linkedSetOf<TrackingIssue>()
    val oldest = s.oldestPendingAtMillis
    val backlog = s.pendingPoints >= params.backlogPoints ||
        (s.online && oldest != null && s.nowMillis - oldest >= params.backlogAgeMillis)
    if (s.pendingPoints > 0 && backlog) issues += TrackingIssue.SYNC_BACKLOG
    if (!s.hasActiveShift) {
        return TrackingStatus(TrackingLevel.IDLE, issues, s.pendingPoints, s.lastFixAtMillis)
    }

    if (!s.locationPermission) issues += TrackingIssue.LOCATION_PERMISSION_DENIED
    if (!s.locationEnabled) issues += TrackingIssue.LOCATION_DISABLED
    if (!s.serviceRunning) issues += TrackingIssue.SERVICE_NOT_RUNNING
    if (s.serviceRunning && s.locationPermission && s.locationEnabled && noRecentFix(s, params)) {
        issues += TrackingIssue.NO_RECENT_FIX
    }
    if (!s.online) issues += TrackingIssue.OFFLINE
    if (!s.backgroundPermission) issues += TrackingIssue.BACKGROUND_PERMISSION_MISSING
    if (!s.batteryOptimizationExempt) issues += TrackingIssue.BATTERY_OPTIMIZED
    if (!s.notificationsAllowed) issues += TrackingIssue.NOTIFICATIONS_BLOCKED

    val level = when {
        TrackingIssue.LOCATION_PERMISSION_DENIED in issues ||
            TrackingIssue.LOCATION_DISABLED in issues -> TrackingLevel.BLOCKED
        TrackingIssue.SERVICE_NOT_RUNNING in issues -> TrackingLevel.STOPPED
        TrackingIssue.NO_RECENT_FIX in issues -> TrackingLevel.WEAK_SIGNAL
        TrackingIssue.OFFLINE in issues -> TrackingLevel.OFFLINE_RECORDING
        else -> TrackingLevel.ACTIVE
    }
    return TrackingStatus(level, issues, s.pendingPoints, s.lastFixAtMillis)
}

private fun noRecentFix(s: TrackingSignals, params: StatusParams): Boolean {
    val threshold = maxOf(params.minNoFixMillis, s.expectedIntervalMillis * 3)
    val reference = s.lastFixAtMillis ?: s.trackingSinceMillis ?: return false
    return s.nowMillis - reference >= threshold
}

/**
 * Turns status changes into device events for the server, so management
 * sees tracking problems (not only the driver). Events are reported only
 * during an active shift; nothing is reported about the phone off-shift.
 */
object TrackingEventDetector {
    private val onEvents = mapOf(
        TrackingIssue.LOCATION_PERMISSION_DENIED to TrackingEventType.PERMISSION_DENIED,
        TrackingIssue.LOCATION_DISABLED to TrackingEventType.LOCATION_DISABLED,
        TrackingIssue.NO_RECENT_FIX to TrackingEventType.GPS_SIGNAL_LOST,
        TrackingIssue.BACKGROUND_PERMISSION_MISSING to TrackingEventType.BACKGROUND_PERMISSION_DENIED,
        TrackingIssue.BATTERY_OPTIMIZED to TrackingEventType.BATTERY_OPTIMIZATION_ENABLED,
        TrackingIssue.SYNC_BACKLOG to TrackingEventType.OFFLINE_QUEUE_BACKLOG,
    )
    private val offEvents = mapOf(
        TrackingIssue.LOCATION_PERMISSION_DENIED to TrackingEventType.PERMISSION_GRANTED,
        TrackingIssue.LOCATION_DISABLED to TrackingEventType.LOCATION_ENABLED,
        TrackingIssue.NO_RECENT_FIX to TrackingEventType.GPS_SIGNAL_RESTORED,
    )

    fun diff(previous: TrackingStatus?, current: TrackingStatus): List<TrackingEventType> {
        if (current.level == TrackingLevel.IDLE) return emptyList()
        val before = if (previous == null || previous.level == TrackingLevel.IDLE) {
            emptySet()
        } else {
            previous.issues
        }
        val raised = onEvents.filterKeys { it in current.issues && it !in before }.values
        val cleared = offEvents.filterKeys { it in before && it !in current.issues }.values
        return raised + cleared
    }
}
