package com.godaily.driver.core.sync

import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.DeviceInfo
import com.godaily.driver.core.api.DriverApi
import com.godaily.driver.core.api.EndShiftRequest
import com.godaily.driver.core.api.PointBatch
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.api.TrackingEvent
import com.godaily.driver.core.api.TrackingEventsRequest
import java.util.UUID

enum class SyncOutcome {
    /** Everything that could be sent was sent. */
    COMPLETE,

    /** A temporary failure (network, server) or more work left; run again later. */
    RETRY,

    /** The token is no longer valid; queues are kept until the driver logs in. */
    AUTH_REQUIRED,
}

data class SyncReport(
    val outcome: SyncOutcome,
    val eventsSent: Int = 0,
    val pointsAccepted: Int = 0,
    val pointsDuplicate: Int = 0,
    /** Points the server refused individually (outside the shift window, future time). */
    val pointsRejected: Int = 0,
    /** Points in batches the server refused as a whole; kept on the phone, not retried. */
    val pointsFailed: Int = 0,
    val endedShift: Shift? = null,
    /** Arabic message from the server when a queued shift end was refused. */
    val shiftEndError: String? = null,
    val error: ApiError? = null,
)

/**
 * Uploads everything queued on the phone: device events first (small and
 * important for management), then GPS batches oldest first, then a shift
 * end confirmed while offline.
 *
 * Safe to run repeatedly and concurrently with recording: every request is
 * idempotent (event ids, batch ids, point ids, Idempotency-Key). Callers
 * must not run two engines at the same time on the same queues.
 */
class SyncEngine(
    private val api: DriverApi,
    private val points: PointQueue,
    private val events: EventQueue,
    private val pendingEnd: PendingShiftEndStore,
    private val device: suspend () -> DeviceInfo = { DeviceInfo() },
    private val newBatchId: () -> String = { UUID.randomUUID().toString() },
    /** Caps one run so a huge backlog is spread over several runs. */
    private val maxBatchesPerRun: Int = 20,
) {
    private class Progress {
        var outcome = SyncOutcome.COMPLETE
        var eventsSent = 0
        var accepted = 0
        var duplicates = 0
        var rejected = 0
        var failed = 0
        var endedShift: Shift? = null
        var shiftEndError: String? = null

        fun report(error: ApiError? = null) = SyncReport(
            outcome, eventsSent, accepted, duplicates, rejected, failed, endedShift, shiftEndError, error,
        )
    }

    suspend fun run(): SyncReport {
        val progress = Progress()
        try {
            sendEvents(progress)
            sendPoints(progress)
            sendShiftEnd(progress)
        } catch (e: ApiError) {
            progress.outcome = if (e is ApiError.Unauthorized) SyncOutcome.AUTH_REQUIRED else SyncOutcome.RETRY
            return progress.report(e)
        }
        return progress.report()
    }

    private suspend fun sendEvents(progress: Progress) {
        while (true) {
            val batch = events.pending(TrackingEventsRequest.MAX_EVENTS)
            if (batch.isEmpty()) return
            try {
                api.uploadEvents(TrackingEventsRequest(batch))
                progress.eventsSent += batch.size
            } catch (e: ApiError.Rejected) {
                // Refused as a whole: retry one by one so a single bad event
                // (e.g. for a shift that is no longer this driver's) cannot
                // block the queue; events refused on their own are dropped.
                if (batch.size > 1) progress.eventsSent += sendIndividually(batch)
            }
            events.remove(batch.map { it.clientEventId })
            if (batch.size < TrackingEventsRequest.MAX_EVENTS) return
        }
    }

    private suspend fun sendIndividually(batch: List<TrackingEvent>): Int = batch.count { event ->
        try {
            api.uploadEvents(TrackingEventsRequest(listOf(event)))
            true
        } catch (_: ApiError.Rejected) {
            false
        }
    }

    private suspend fun sendPoints(progress: Progress) {
        repeat(maxBatchesPerRun) {
            val batch = points.inFlightBatch()
                ?: points.claimBatch(newBatchId(), PointBatch.MAX_POINTS)
                ?: return
            val info = device().copy(pendingPoints = points.pendingCount())
            try {
                val result = api.uploadPoints(PointBatch(batch.batchId, batch.shiftId, batch.points, info))
                points.acknowledge(batch.batchId)
                progress.accepted += result.accepted
                progress.duplicates += result.duplicates
                progress.rejected += result.rejected.size
            } catch (e: ApiError.Rejected) {
                points.markFailed(batch.batchId, e.code)
                progress.failed += batch.points.size
            }
        }
        // Stopped at the per-run cap with work left: ask to be run again.
        if (points.pendingCount() > 0) progress.outcome = SyncOutcome.RETRY
    }

    private suspend fun sendShiftEnd(progress: Progress) {
        val end = pendingEnd.get() ?: return
        try {
            progress.endedShift = api.endShift(
                end.shiftId,
                EndShiftRequest(endOdometerKm = end.endOdometerKm, notes = end.notes),
                end.idempotencyKey,
            )
        } catch (e: ApiError.Rejected) {
            // e.g. the shift was already ended or cancelled from the office.
            progress.shiftEndError = e.message
        }
        pendingEnd.clear()
    }
}
