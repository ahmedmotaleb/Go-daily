package com.godaily.driver.sync

import com.godaily.driver.core.sync.SyncEngine
import com.godaily.driver.core.sync.SyncOutcome
import com.godaily.driver.core.sync.SyncReport
import com.godaily.driver.data.ShiftStateStore
import com.godaily.driver.data.SqlitePointQueue
import com.godaily.driver.security.KeystoreTokenStore
import java.time.Duration
import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Runs the core [SyncEngine] for the service, the worker and the UI, one
 * run at a time per process, and applies its results to local state.
 */
class Syncer(
    private val engine: SyncEngine,
    private val tokens: KeystoreTokenStore,
    private val shiftState: ShiftStateStore,
    private val points: SqlitePointQueue,
) {
    private val mutex = Mutex()
    private val _lastReport = MutableStateFlow<SyncReport?>(null)
    private val _sessionExpired = MutableStateFlow(false)

    val lastReport: StateFlow<SyncReport?> = _lastReport

    /** The server rejected the token; queues are kept until the next login. */
    val sessionExpired: StateFlow<Boolean> = _sessionExpired

    suspend fun syncNow(): SyncReport {
        if (tokens.token() == null) return SyncReport(SyncOutcome.AUTH_REQUIRED)
        val report = mutex.withLock { engine.run() }
        if (report.outcome == SyncOutcome.AUTH_REQUIRED) _sessionExpired.value = true
        report.shiftEndError?.let { shiftState.lastShiftEndError = it }
        if (report.error == null) shiftState.lastSyncAtMillis = System.currentTimeMillis()
        points.pruneFailed(Instant.now().minus(FAILED_RETENTION))
        _lastReport.value = report
        return report
    }

    fun onLoggedIn() {
        _sessionExpired.value = false
    }

    private companion object {
        val FAILED_RETENTION: Duration = Duration.ofDays(7)
    }
}
