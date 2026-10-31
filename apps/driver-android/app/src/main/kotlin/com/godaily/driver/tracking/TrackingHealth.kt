package com.godaily.driver.tracking

import com.godaily.driver.AppContainer
import com.godaily.driver.core.api.TrackingEvent
import com.godaily.driver.core.api.TrackingEventType
import com.godaily.driver.core.tracking.TrackingEventDetector
import com.godaily.driver.core.tracking.TrackingLevel
import com.godaily.driver.core.tracking.TrackingSignals
import com.godaily.driver.core.tracking.TrackingStatus
import com.godaily.driver.core.tracking.evaluateTracking
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Evaluates tracking health, publishes it to the UI and notification, and
 * queues device events for problems that start or end during a shift.
 * Called by the service on every tick and by the UI while visible.
 */
class TrackingHealth(private val c: AppContainer) {
    private val mutex = Mutex()

    suspend fun check(): TrackingStatus = mutex.withLock {
        val shiftId = c.shiftState.activeShiftId
        val status = evaluateTracking(signals())
        val previous = c.shiftState.reportedIssues(shiftId)?.let {
            TrackingStatus(TrackingLevel.ACTIVE, it, pendingPoints = 0, lastFixAtMillis = null)
        }
        TrackingEventDetector.diff(previous, status).forEach { record(it) }
        if (shiftId != null && status.level != TrackingLevel.IDLE) {
            c.shiftState.saveReportedIssues(shiftId, status.issues)
        }
        TrackingMonitor.status.value = status
        status
    }

    suspend fun record(
        type: TrackingEventType,
        shiftId: String? = c.shiftState.activeShiftId,
        details: Map<String, String>? = null,
    ) {
        c.eventQueue.enqueue(
            TrackingEvent(
                clientEventId = UUID.randomUUID().toString(),
                eventType = type,
                occurredAt = Instant.now(),
                shiftId = shiftId,
                details = details?.let { map -> JsonObject(map.mapValues { JsonPrimitive(it.value) }) },
            ),
        )
    }

    private suspend fun signals(): TrackingSignals {
        val service = TrackingMonitor.service.value
        val device = c.device
        return TrackingSignals(
            hasActiveShift = c.shiftState.activeShiftId != null,
            locationPermission = device.hasFineLocation(),
            backgroundPermission = device.hasBackgroundLocation(),
            notificationsAllowed = device.notificationsAllowed(),
            locationEnabled = device.locationEnabled(),
            serviceRunning = service.running,
            trackingSinceMillis = service.sinceMillis,
            lastFixAtMillis = service.lastFixAtMillis,
            nowMillis = System.currentTimeMillis(),
            online = device.online(),
            pendingPoints = c.pointQueue.pendingCount(),
            oldestPendingAtMillis = c.pointQueue.oldestPendingAt()?.toEpochMilli(),
            batteryOptimizationExempt = device.batteryOptimizationExempt(),
            expectedIntervalMillis = service.intervalMillis,
        )
    }
}
