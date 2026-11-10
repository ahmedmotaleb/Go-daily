package com.godaily.driver.core.tracking

import com.godaily.driver.core.text.ArabicText
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class TrackingChecksTest {
    private fun status(level: TrackingLevel, vararg issues: TrackingIssue) =
        TrackingStatus(level, issues.toSet(), pendingPoints = 0, lastFixAtMillis = null)

    private fun List<TrackingCheck>.of(kind: CheckKind) = first { it.kind == kind }

    @Test
    fun `outside a shift nothing is claimed to be fine`() {
        for (s in listOf(null, status(TrackingLevel.IDLE), status(TrackingLevel.IDLE, TrackingIssue.SYNC_BACKLOG))) {
            val checks = trackingChecks(s)
            assertEquals(CheckKind.entries.size, checks.size)
            assertTrue(checks.all { it.state == CheckState.NOT_CHECKED })
            assertEquals("يُفحص عند بدء الوردية", ArabicText.checkState(checks.first()))
        }
    }

    @Test
    fun `a healthy shift shows every requirement as ok`() {
        val checks = trackingChecks(status(TrackingLevel.ACTIVE))
        assertTrue(checks.all { it.state == CheckState.OK })
        assertEquals("مسموح طوال الوقت", ArabicText.checkState(checks.of(CheckKind.LOCATION_PERMISSION)))
    }

    @Test
    fun `blocking issues are problems and the rest are warnings`() {
        val checks = trackingChecks(
            status(
                TrackingLevel.PERMISSION_REQUIRED,
                TrackingIssue.LOCATION_PERMISSION_DENIED,
                TrackingIssue.BACKGROUND_PERMISSION_MISSING,
                TrackingIssue.OFFLINE,
                TrackingIssue.BATTERY_OPTIMIZED,
            ),
        )
        // Denied outranks "while using the app only" on the same requirement.
        assertEquals(CheckState.PROBLEM, checks.of(CheckKind.LOCATION_PERMISSION).state)
        assertEquals(TrackingIssue.LOCATION_PERMISSION_DENIED, checks.of(CheckKind.LOCATION_PERMISSION).issue)
        assertEquals(CheckState.WARNING, checks.of(CheckKind.INTERNET).state)
        assertEquals(CheckState.WARNING, checks.of(CheckKind.BATTERY).state)
        assertEquals(CheckState.OK, checks.of(CheckKind.PHONE_GPS).state)
        assertEquals("غير متصل الآن — المواقع محفوظة على الهاتف", ArabicText.checkState(checks.of(CheckKind.INTERNET)))
    }

    @Test
    fun `location switch off is a problem, no recent fix a warning`() {
        assertEquals(
            CheckState.PROBLEM,
            trackingChecks(status(TrackingLevel.LOCATION_OFF, TrackingIssue.LOCATION_DISABLED)).of(CheckKind.PHONE_GPS).state,
        )
        assertEquals(
            CheckState.WARNING,
            trackingChecks(status(TrackingLevel.WEAK_SIGNAL, TrackingIssue.NO_RECENT_FIX)).of(CheckKind.PHONE_GPS).state,
        )
    }

    @Test
    fun `greeting uses the first name and the time of day`() {
        assertEquals("صباح الخير، محمود", ArabicText.greeting(8, "محمود علي"))
        assertEquals("مساء الخير، محمود", ArabicText.greeting(19, "محمود"))
        assertEquals("مساء الخير", ArabicText.greeting(2, null))
        assertEquals("صباح الخير", ArabicText.greeting(4, "  "))
    }

    @Test
    fun `ages read as short relative times`() {
        assertEquals("الآن", ArabicText.since(3))
        assertEquals("منذ 42 ث", ArabicText.since(42))
        assertEquals("منذ 4 د", ArabicText.since(4 * 60 + 59))
        assertEquals("منذ 2 س", ArabicText.since(2 * 3_600 + 10))
    }
}
