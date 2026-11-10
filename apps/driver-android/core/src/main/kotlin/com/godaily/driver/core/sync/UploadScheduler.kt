package com.godaily.driver.core.sync

/**
 * Decides when the tracking service uploads queued points.
 *
 * The admin live map treats a vehicle as online for 120 s after its last
 * point, so while online the service flushes at least every [maxAgeMillis].
 * Failures back off exponentially (with jitter); regaining connectivity
 * clears the backoff so the backlog goes out right away.
 */
class UploadScheduler(
    private val backoff: Backoff = Backoff(),
    private val maxAgeMillis: Long = 45_000,
    private val maxPending: Int = 60,
) {
    private var failures = 0
    private var notBefore = 0L
    private var authBlocked = false

    val consecutiveFailures: Int get() = failures

    fun isDue(nowMillis: Long, pending: Int, oldestPendingAtMillis: Long?, online: Boolean): Boolean {
        if (!online || authBlocked || pending <= 0 || nowMillis < notBefore) return false
        if (pending >= maxPending) return true
        return oldestPendingAtMillis != null && nowMillis - oldestPendingAtMillis >= maxAgeMillis
    }

    fun onResult(nowMillis: Long, report: SyncReport) {
        when {
            report.outcome == SyncOutcome.AUTH_REQUIRED -> authBlocked = true
            report.error != null -> {
                notBefore = nowMillis + backoff.delayFor(failures).inWholeMilliseconds
                failures += 1
            }
            else -> {
                failures = 0
                notBefore = 0
            }
        }
    }

    fun onConnectivityRegained() {
        failures = 0
        notBefore = 0
    }

    fun onLoggedIn() {
        authBlocked = false
        onConnectivityRegained()
    }
}
