package com.godaily.driver.core.sync

import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.GpsPoint
import com.godaily.driver.core.api.TrackingEvent
import com.godaily.driver.core.api.TrackingEventType
import java.time.Instant
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

private val T0: Instant = Instant.parse("2026-03-01T06:30:00Z")

private fun point(i: Int, prefix: String = "p") = GpsPoint(
    clientPointId = "$prefix-$i",
    recordedAt = T0.plusSeconds(i * 10L),
    latitude = 31.04,
    longitude = 31.37 + i * 0.0001,
    accuracyM = 8.0,
)

private fun event(id: String, type: TrackingEventType = TrackingEventType.GPS_SIGNAL_LOST) =
    TrackingEvent(id, type, T0, shiftId = "s1")

class SyncEngineTest {
    private val api = FakeDriverApi()
    private val points = InMemoryPointQueue()
    private val events = InMemoryEventQueue()
    private val ends = InMemoryShiftEndStore()
    private var batchSeq = 0
    private val engine = SyncEngine(api, points, events, ends, newBatchId = { "b${batchSeq++}" })

    @Test
    fun `uploads the queue in batches of at most 500 and empties it`() = runTest {
        repeat(1_200) { points.enqueue("s1", point(it)) }
        val report = engine.run()
        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(listOf(500, 500, 200), api.uploadedBatches.map { it.points.size })
        assertEquals(1_200, report.pointsAccepted)
        assertEquals(0, points.pendingCount())
        // Oldest first, in recording order.
        assertEquals("p-0", api.uploadedBatches.first().points.first().clientPointId)
    }

    @Test
    fun `a failed upload is retried with the same batch id and points`() = runTest {
        repeat(30) { points.enqueue("s1", point(it)) }
        api.failures += offline()
        val first = engine.run()
        assertEquals(SyncOutcome.RETRY, first.outcome)
        assertEquals(30, points.pendingCount())

        val second = engine.run()
        assertEquals(SyncOutcome.COMPLETE, second.outcome)
        assertEquals(1, api.uploadedBatches.size)
        assertEquals("b0", api.uploadedBatches.single().batchId)
        assertEquals(30, second.pointsAccepted)
    }

    @Test
    fun `a lost response is answered by the server's batch replay without duplicates`() = runTest {
        repeat(10) { points.enqueue("s1", point(it)) }
        // The server stored the batch but the phone never saw the answer.
        val claimed = points.claimBatch("b-lost", 500)!!
        api.uploadPoints(com.godaily.driver.core.api.PointBatch(claimed.batchId, claimed.shiftId, claimed.points))

        val report = engine.run()
        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(listOf("b-lost", "b-lost"), api.uploadedBatches.map { it.batchId })
        assertEquals(10, api.storedPointIds.size)
        assertEquals(0, points.pendingCount())
    }

    @Test
    fun `batches never mix shifts`() = runTest {
        repeat(3) { points.enqueue("s1", point(it, "a")) }
        repeat(3) { points.enqueue("s2", point(it + 100, "b")) }
        engine.run()
        assertEquals(listOf("s1", "s2"), api.uploadedBatches.map { it.shiftId })
        assertTrue(api.uploadedBatches[0].points.all { it.clientPointId.startsWith("a") })
    }

    @Test
    fun `expired login keeps everything queued`() = runTest {
        repeat(5) { points.enqueue("s1", point(it)) }
        events.enqueue(event("e1"))
        api.failures += ApiError.Unauthorized("invalid_token", "انتهت الجلسة")
        val report = engine.run()
        assertEquals(SyncOutcome.AUTH_REQUIRED, report.outcome)
        assertEquals(5, points.pendingCount())
        assertEquals(1, events.items.size)
    }

    @Test
    fun `a batch refused as a whole is set aside and the rest still uploads`() = runTest {
        repeat(3) { points.enqueue("gone", point(it, "x")) }
        repeat(3) { points.enqueue("s1", point(it + 50)) }
        api.failures += ApiError.Rejected(404, "not_found", "الوردية غير موجودة")
        val report = engine.run()
        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(3, report.pointsFailed)
        assertEquals(3, report.pointsAccepted)
        assertEquals(listOf("not_found", "not_found", "not_found"), points.failedReasons)
        assertEquals(0, points.pendingCount())
    }

    @Test
    fun `points outside the shift window are reported, not retried`() = runTest {
        repeat(4) { points.enqueue("s1", point(it)) }
        api.outsideWindow = { it.clientPointId == "p-3" }
        val report = engine.run()
        assertEquals(3, report.pointsAccepted)
        assertEquals(1, report.pointsRejected)
        assertEquals(0, points.pendingCount())
    }

    @Test
    fun `a huge backlog is spread over several runs`() = runTest {
        val small = SyncEngine(api, points, events, ends, newBatchId = { "c${batchSeq++}" }, maxBatchesPerRun = 2)
        repeat(1_500) { points.enqueue("s1", point(it)) }
        val first = small.run()
        assertEquals(SyncOutcome.RETRY, first.outcome)
        assertNull(first.error)
        assertEquals(500, points.pendingCount())
        assertEquals(SyncOutcome.COMPLETE, small.run().outcome)
        assertEquals(1_500, api.storedPointIds.size)
    }

    @Test
    fun `device events go first and a bad one cannot block the others`() = runTest {
        events.enqueue(event("e1"))
        events.enqueue(event("bad"))
        events.enqueue(event("e3", TrackingEventType.GPS_SIGNAL_RESTORED))
        points.enqueue("s1", point(1))
        api.rejectEvent = { it.clientEventId == "bad" }
        val report = engine.run()
        assertEquals(2, report.eventsSent)
        assertEquals(setOf("e1", "e3"), api.storedEventIds)
        assertTrue(events.items.isEmpty())
        assertEquals(1, report.pointsAccepted)
    }

    @Test
    fun `shift ended offline is sent after its points with a stable idempotency key`() = runTest {
        repeat(20) { points.enqueue("s1", point(it)) }
        ends.value = PendingShiftEnd("s1", 120_450, null, "key-1", T0.plusSeconds(600))

        api.failures += offline()
        val offlineRun = engine.run()
        assertEquals(SyncOutcome.RETRY, offlineRun.outcome)
        assertNotNull(ends.value)
        assertEquals(20, points.pendingCount())

        val report = engine.run()
        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(20, report.pointsAccepted)
        assertEquals(listOf("s1" to "key-1"), api.endCalls)
        assertEquals("s1", report.endedShift?.id)
        assertNull(ends.value)
    }

    @Test
    fun `a queued shift end refused by the server is dropped with its message`() = runTest {
        ends.value = PendingShiftEnd("s1", 100, null, "key-2", T0)
        api.endFailure = ApiError.Rejected(409, "invalid_shift_state", "الوردية ليست نشطة")
        val report = engine.run()
        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals("الوردية ليست نشطة", report.shiftEndError)
        assertNull(ends.value)
    }
}
