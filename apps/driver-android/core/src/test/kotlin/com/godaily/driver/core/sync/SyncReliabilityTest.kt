package com.godaily.driver.core.sync

import com.godaily.driver.core.api.GpsPoint
import com.godaily.driver.core.api.PointBatch
import java.time.Instant
import kotlin.random.Random
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

private val START: Instant = Instant.parse("2026-03-01T05:00:00Z")

private fun fix(i: Int) = GpsPoint(
    clientPointId = "pt-$i",
    recordedAt = START.plusSeconds(i * 10L),
    latitude = 30.04,
    longitude = 31.23 + i * 0.00005,
    accuracyM = 6.0,
)

/** Task 29: the scenarios a phone goes through during a real shift. */
class SyncReliabilityTest {
    private val api = FakeDriverApi()
    private val points = InMemoryPointQueue()
    private val events = InMemoryEventQueue()
    private val ends = InMemoryShiftEndStore()

    private fun engine(prefix: String, maxBatches: Int = 3): SyncEngine {
        var seq = 0
        return SyncEngine(
            api, points, events, ends,
            newBatchId = { "$prefix-${seq++}" },
            maxBatchesPerRun = maxBatches,
        )
    }

    private suspend fun drain(engine: SyncEngine): SyncReport {
        var report = engine.run()
        while (report.outcome == SyncOutcome.RETRY) report = engine.run()
        return report
    }

    @Test
    fun `after a process restart the in-flight batch is resumed with its original id`() = runTest {
        repeat(1_400) { points.enqueue("s1", fix(it)) }
        ends.value = PendingShiftEnd("s1", 50_200, null, "end-key", START.plusSeconds(20_000))

        // First process: one batch goes through, the next fails (signal lost), then the app is killed.
        val first = engine("A", maxBatches = 1)
        assertEquals(SyncOutcome.RETRY, first.run().outcome)
        api.failures += offline()
        assertEquals(SyncOutcome.RETRY, first.run().outcome)
        val interrupted = points.inFlightBatch()
        assertEquals("A-1", interrupted?.batchId)

        // New process: a fresh engine (new id generator) over the same stored queue,
        // with fixes recorded after the restart.
        repeat(50) { points.enqueue("s1", fix(10_000 + it)) }
        val report = drain(engine("B"))

        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(listOf("A-0", "A-1", "B-0"), api.uploadedBatches.map { it.batchId })
        assertEquals(1_450, api.storedPointIds.size) // every fix exactly once
        assertEquals(0, points.pendingCount())
        // The shift end went last, once, with the key chosen when the driver ended the shift.
        assertEquals(listOf("s1" to "end-key"), api.endCalls)
        assertNull(ends.value)
    }

    @Test
    fun `a long shift with random signal loss and lost answers stores every fix exactly once`() = runTest {
        val random = Random(29) // fixed seed: reproducible
        val sync = engine("R")
        var recorded = 0
        repeat(200) { cycle ->
            // The phone keeps recording whatever the network does.
            repeat(random.nextInt(0, 40)) { points.enqueue("s1", fix(recorded++)) }
            when (random.nextInt(10)) {
                0, 1, 2 -> {
                    // No signal: the upload attempt fails before reaching the server.
                    api.failures += offline()
                    sync.run()
                }
                3 -> {
                    // The server stores a batch but the phone never sees the answer.
                    val batch = points.inFlightBatch() ?: points.claimBatch("lost-$cycle", PointBatch.MAX_POINTS)
                    if (batch != null) api.uploadPoints(PointBatch(batch.batchId, batch.shiftId, batch.points))
                }
                else -> sync.run()
            }
        }
        // Back in coverage at the end of the shift.
        api.failures.clear()
        val report = drain(sync)

        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(recorded, api.storedPointIds.size)
        assertEquals(0, points.pendingCount())
        // Batches go oldest first, so the server receives fixes in recording order.
        val firstSeen = api.uploadedBatches.flatMap { b -> b.points.map { it.clientPointId } }.distinct()
        assertEquals((0 until recorded).map { "pt-$it" }, firstSeen)
    }
}
