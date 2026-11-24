package com.godaily.driver.core.sync

import com.godaily.driver.core.api.GpsPoint
import com.godaily.driver.core.api.TrackingEvent
import java.time.Instant

/** Points of one shift that travel together under one upload batch id. */
data class PendingBatch(val batchId: String, val shiftId: String, val points: List<GpsPoint>)

/**
 * Durable on-device queue of GPS points (SQLite on Android).
 *
 * Batch contents are fixed once claimed: a retry re-sends exactly the same
 * points under the same batch id, which the server recognises and answers
 * from its record instead of ingesting twice.
 */
interface PointQueue {
    suspend fun enqueue(shiftId: String, point: GpsPoint)

    /** The batch claimed earlier but never acknowledged, if any. */
    suspend fun inFlightBatch(): PendingBatch?

    /**
     * Claims up to [limit] of the oldest unclaimed points that belong to the
     * same shift as the oldest one, under [batchId]. Null when empty.
     */
    suspend fun claimBatch(batchId: String, limit: Int): PendingBatch?

    /** Server acknowledged the batch: remove its points from the phone. */
    suspend fun acknowledge(batchId: String)

    /**
     * The server refused the whole batch (it can never be accepted as is).
     * Points are kept, marked failed, for diagnostics; they are not retried.
     */
    suspend fun markFailed(batchId: String, reason: String)

    suspend fun pendingCount(): Int

    suspend fun oldestPendingAt(): Instant?
}

interface EventQueue {
    suspend fun enqueue(event: TrackingEvent)

    suspend fun pending(limit: Int): List<TrackingEvent>

    suspend fun remove(clientEventIds: Collection<String>)
}

/** A shift end the driver confirmed while the request could not be sent yet. */
data class PendingShiftEnd(
    val shiftId: String,
    val endOdometerKm: Int,
    val notes: String?,
    val idempotencyKey: String,
    val requestedAt: Instant,
)

interface PendingShiftEndStore {
    suspend fun get(): PendingShiftEnd?

    suspend fun clear()
}
