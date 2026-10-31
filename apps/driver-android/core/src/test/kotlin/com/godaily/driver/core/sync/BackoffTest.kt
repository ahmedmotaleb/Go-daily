package com.godaily.driver.core.sync

import kotlin.random.Random
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class BackoffTest {
    @Test
    fun `delays grow exponentially and stay under the cap`() {
        val backoff = Backoff(base = 5.seconds, cap = 15.minutes, random = Random(42))
        repeat(50) { attempt ->
            val ceiling = minOf(5.seconds * (1 shl minOf(attempt, 20)), 15.minutes)
            val d = backoff.delayFor(attempt)
            assertTrue(d >= 0.seconds && d <= ceiling, "attempt $attempt gave $d")
        }
    }

    @Test
    fun `jitter spreads retries`() {
        val backoff = Backoff(random = Random(7))
        val delays = (1..20).map { backoff.delayFor(6) }.toSet()
        assertTrue(delays.size > 10)
    }

    @Test
    fun `invalid bounds are refused`() {
        assertThrows<IllegalArgumentException> { Backoff(base = 10.seconds, cap = 1.seconds) }
        assertThrows<IllegalArgumentException> { Backoff().delayFor(-1) }
    }

    @Test
    fun `scheduler flushes on age or size and backs off after failures`() {
        val scheduler = UploadScheduler(Backoff(base = 10.seconds, cap = 10.seconds, random = Random(1)))
        assertFalse(scheduler.isDue(100_000, pending = 5, oldestPendingAtMillis = 90_000, online = true))
        assertTrue(scheduler.isDue(100_000, pending = 5, oldestPendingAtMillis = 50_000, online = true))
        assertTrue(scheduler.isDue(100_000, pending = 60, oldestPendingAtMillis = 99_000, online = true))
        assertFalse(scheduler.isDue(100_000, pending = 60, oldestPendingAtMillis = 0, online = false))
        assertFalse(scheduler.isDue(100_000, pending = 0, oldestPendingAtMillis = null, online = true))

        scheduler.onResult(100_000, SyncReport(SyncOutcome.RETRY, error = offline()))
        assertEquals(1, scheduler.consecutiveFailures)
        assertFalse(scheduler.isDue(100_000, pending = 60, oldestPendingAtMillis = 0, online = true))
        assertTrue(scheduler.isDue(110_001, pending = 60, oldestPendingAtMillis = 0, online = true))

        scheduler.onResult(110_001, SyncReport(SyncOutcome.RETRY, error = offline()))
        scheduler.onConnectivityRegained()
        assertTrue(scheduler.isDue(110_002, pending = 60, oldestPendingAtMillis = 0, online = true))

        scheduler.onResult(110_002, SyncReport(SyncOutcome.AUTH_REQUIRED))
        assertFalse(scheduler.isDue(999_999, pending = 60, oldestPendingAtMillis = 0, online = true))
        scheduler.onLoggedIn()
        assertTrue(scheduler.isDue(999_999, pending = 60, oldestPendingAtMillis = 0, online = true))
    }
}
