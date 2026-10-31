package com.godaily.driver.core.tracking

import com.godaily.driver.core.api.TrackingEventType
import com.godaily.driver.core.text.ArabicText
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TrackingStatusTest {
    private val now = 10_000_000L
    private val healthy = TrackingSignals(
        hasActiveShift = true,
        locationPermission = true,
        backgroundPermission = true,
        notificationsAllowed = true,
        locationEnabled = true,
        serviceRunning = true,
        trackingSinceMillis = now - 600_000,
        lastFixAtMillis = now - 5_000,
        nowMillis = now,
        online = true,
        pendingPoints = 3,
        oldestPendingAtMillis = now - 20_000,
        batteryOptimizationExempt = true,
        expectedIntervalMillis = 10_000,
    )

    @Test
    fun `healthy tracking is active with no issues`() {
        val status = evaluateTracking(healthy)
        assertEquals(TrackingLevel.ACTIVE, status.level)
        assertTrue(status.issues.isEmpty())
    }

    @Test
    fun `offline but recording is its own state`() {
        val status = evaluateTracking(healthy.copy(online = false))
        assertEquals(TrackingLevel.OFFLINE_RECORDING, status.level)
    }

    @Test
    fun `permission or location switch problems block tracking`() {
        assertEquals(TrackingLevel.BLOCKED, evaluateTracking(healthy.copy(locationPermission = false)).level)
        val off = evaluateTracking(healthy.copy(locationEnabled = false, online = false))
        assertEquals(TrackingLevel.BLOCKED, off.level)
        assertTrue(TrackingIssue.OFFLINE in off.issues)
    }

    @Test
    fun `a stopped service during a shift is visible`() {
        val status = evaluateTracking(healthy.copy(serviceRunning = false, trackingSinceMillis = null))
        assertEquals(TrackingLevel.STOPPED, status.level)
    }

    @Test
    fun `no fix for several intervals means weak signal`() {
        val stale = healthy.copy(lastFixAtMillis = now - 130_000)
        assertEquals(TrackingLevel.WEAK_SIGNAL, evaluateTracking(stale).level)
        // Slow (parked) sampling widens the threshold to three intervals.
        val parked = stale.copy(expectedIntervalMillis = 60_000)
        assertEquals(TrackingLevel.ACTIVE, evaluateTracking(parked).level)
        // Never got a first fix since the service started.
        val noFirstFix = healthy.copy(lastFixAtMillis = null, trackingSinceMillis = now - 200_000)
        assertEquals(TrackingLevel.WEAK_SIGNAL, evaluateTracking(noFirstFix).level)
    }

    @Test
    fun `warnings do not change the headline state`() {
        val status = evaluateTracking(
            healthy.copy(backgroundPermission = false, batteryOptimizationExempt = false, notificationsAllowed = false),
        )
        assertEquals(TrackingLevel.ACTIVE, status.level)
        assertEquals(
            setOf(
                TrackingIssue.BACKGROUND_PERMISSION_MISSING,
                TrackingIssue.BATTERY_OPTIMIZED,
                TrackingIssue.NOTIFICATIONS_BLOCKED,
            ),
            status.issues,
        )
    }

    @Test
    fun `old or large backlogs are flagged`() {
        val old = evaluateTracking(healthy.copy(oldestPendingAtMillis = now - 11 * 60_000))
        assertTrue(TrackingIssue.SYNC_BACKLOG in old.issues)
        // Offline: age alone is expected, only size counts.
        val offline = evaluateTracking(healthy.copy(online = false, oldestPendingAtMillis = now - 60 * 60_000))
        assertTrue(TrackingIssue.SYNC_BACKLOG !in offline.issues)
        val big = evaluateTracking(healthy.copy(online = false, pendingPoints = 2_500))
        assertTrue(TrackingIssue.SYNC_BACKLOG in big.issues)
    }

    @Test
    fun `no shift means idle, whatever the phone's state`() {
        val status = evaluateTracking(
            healthy.copy(hasActiveShift = false, locationPermission = false, serviceRunning = false, pendingPoints = 0),
        )
        assertEquals(TrackingLevel.IDLE, status.level)
        assertTrue(status.issues.isEmpty())
    }

    @Test
    fun `problems present at shift start are reported once`() {
        val start = evaluateTracking(healthy.copy(batteryOptimizationExempt = false, backgroundPermission = false))
        assertEquals(
            listOf(TrackingEventType.BACKGROUND_PERMISSION_DENIED, TrackingEventType.BATTERY_OPTIMIZATION_ENABLED),
            TrackingEventDetector.diff(null, start).sorted(),
        )
        assertEquals(emptyList<TrackingEventType>(), TrackingEventDetector.diff(start, start))
    }

    @Test
    fun `transitions produce lost and restored events`() {
        val ok = evaluateTracking(healthy)
        val lost = evaluateTracking(healthy.copy(lastFixAtMillis = now - 300_000))
        assertEquals(listOf(TrackingEventType.GPS_SIGNAL_LOST), TrackingEventDetector.diff(ok, lost))
        assertEquals(listOf(TrackingEventType.GPS_SIGNAL_RESTORED), TrackingEventDetector.diff(lost, ok))

        val denied = evaluateTracking(healthy.copy(locationPermission = false))
        assertEquals(listOf(TrackingEventType.PERMISSION_DENIED), TrackingEventDetector.diff(ok, denied))
        assertEquals(listOf(TrackingEventType.PERMISSION_GRANTED), TrackingEventDetector.diff(denied, ok))

        val switchedOff = evaluateTracking(healthy.copy(locationEnabled = false))
        assertEquals(listOf(TrackingEventType.LOCATION_DISABLED), TrackingEventDetector.diff(ok, switchedOff))
        assertEquals(listOf(TrackingEventType.LOCATION_ENABLED), TrackingEventDetector.diff(switchedOff, ok))
    }

    @Test
    fun `nothing is reported off shift`() {
        val idle = evaluateTracking(healthy.copy(hasActiveShift = false, locationPermission = false))
        assertTrue(TrackingEventDetector.diff(evaluateTracking(healthy), idle).isEmpty())
    }

    @Test
    fun `every state and issue has Arabic copy`() {
        TrackingLevel.entries.forEach { assertTrue(ArabicText.level(it).isNotBlank()) }
        TrackingIssue.entries.forEach { assertTrue(ArabicText.issue(it).isNotBlank()) }
        assertEquals("كل النقاط مُرسلة", ArabicText.pending(0))
        assertEquals("5 نقاط بانتظار الإرسال", ArabicText.pending(5))
        assertEquals("120 نقطة بانتظار الإرسال", ArabicText.pending(120))
    }
}
