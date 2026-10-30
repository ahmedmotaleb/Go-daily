package com.godaily.driver.core.sync

import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.DriverApi
import com.godaily.driver.core.api.DriverCatalog
import com.godaily.driver.core.api.DriverMe
import com.godaily.driver.core.api.EndShiftRequest
import com.godaily.driver.core.api.FuelEntry
import com.godaily.driver.core.api.FuelEntryRequest
import com.godaily.driver.core.api.GpsPoint
import com.godaily.driver.core.api.LoginRequest
import com.godaily.driver.core.api.LoginResponse
import com.godaily.driver.core.api.PointBatch
import com.godaily.driver.core.api.PointBatchResult
import com.godaily.driver.core.api.RejectedPoint
import com.godaily.driver.core.api.ServerTrackingStatus
import com.godaily.driver.core.api.Session
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.api.StartSessionRequest
import com.godaily.driver.core.api.StartShiftRequest
import com.godaily.driver.core.api.TrackingEvent
import com.godaily.driver.core.api.TrackingEventsRequest
import com.godaily.driver.core.api.TrackingEventsResult
import com.godaily.driver.core.api.VehicleRef
import java.io.IOException
import java.time.Instant

/** Reference implementation of the queue contract (the SQLite one mirrors it). */
class InMemoryPointQueue : PointQueue {
    private data class Row(
        val seq: Long,
        val shiftId: String,
        val point: GpsPoint,
        var batchId: String? = null,
        var failed: String? = null,
    )

    private val rows = mutableListOf<Row>()
    private var seq = 0L
    val failedReasons: List<String> get() = rows.mapNotNull { it.failed }

    override suspend fun enqueue(shiftId: String, point: GpsPoint) {
        if (rows.any { it.point.clientPointId == point.clientPointId }) return
        rows += Row(seq++, shiftId, point)
    }

    override suspend fun inFlightBatch(): PendingBatch? {
        val first = rows.filter { it.batchId != null && it.failed == null }.minByOrNull { it.seq } ?: return null
        val members = rows.filter { it.batchId == first.batchId }
        return PendingBatch(first.batchId!!, first.shiftId, members.sortedBy { it.point.recordedAt }.map { it.point })
    }

    override suspend fun claimBatch(batchId: String, limit: Int): PendingBatch? {
        val open = rows.filter { it.batchId == null && it.failed == null }
            .sortedWith(compareBy({ it.point.recordedAt }, { it.seq }))
        val shift = open.firstOrNull()?.shiftId ?: return null
        val chosen = open.filter { it.shiftId == shift }.take(limit)
        chosen.forEach { it.batchId = batchId }
        return PendingBatch(batchId, shift, chosen.map { it.point })
    }

    override suspend fun acknowledge(batchId: String) {
        rows.removeAll { it.batchId == batchId && it.failed == null }
    }

    override suspend fun markFailed(batchId: String, reason: String) {
        rows.filter { it.batchId == batchId }.forEach { it.failed = reason }
    }

    override suspend fun pendingCount(): Int = rows.count { it.failed == null }

    override suspend fun oldestPendingAt(): Instant? =
        rows.filter { it.failed == null }.minOfOrNull { it.point.recordedAt }
}

class InMemoryEventQueue : EventQueue {
    val items = mutableListOf<TrackingEvent>()

    override suspend fun enqueue(event: TrackingEvent) {
        if (items.none { it.clientEventId == event.clientEventId }) items += event
    }

    override suspend fun pending(limit: Int): List<TrackingEvent> = items.take(limit)

    override suspend fun remove(clientEventIds: Collection<String>) {
        items.removeAll { it.clientEventId in clientEventIds }
    }
}

class InMemoryShiftEndStore(var value: PendingShiftEnd? = null) : PendingShiftEndStore {
    override suspend fun get(): PendingShiftEnd? = value

    override suspend fun clear() {
        value = null
    }
}

fun shift(id: String = "s1", status: String = "COMPLETED") = Shift(
    id = id,
    vehicle = VehicleRef("v1", "MB-01", "ق ط ر 123"),
    status = status,
)

/**
 * Scriptable server: behaves like the real ingestion endpoint (batch replay
 * by id, per-point dedupe, window rejections) unless a failure is queued.
 */
class FakeDriverApi : DriverApi {
    val failures = ArrayDeque<ApiError>()
    val uploadedBatches = mutableListOf<PointBatch>()
    val storedPointIds = mutableSetOf<String>()
    private val seenBatches = mutableMapOf<String, PointBatchResult>()
    val eventCalls = mutableListOf<List<TrackingEvent>>()
    val storedEventIds = mutableSetOf<String>()
    var rejectEvent: (TrackingEvent) -> Boolean = { false }
    var outsideWindow: (GpsPoint) -> Boolean = { false }
    val endCalls = mutableListOf<Pair<String, String>>()
    var endFailure: ApiError? = null

    private fun maybeFail() {
        failures.removeFirstOrNull()?.let { throw it }
    }

    override suspend fun uploadPoints(batch: PointBatch): PointBatchResult {
        maybeFail()
        uploadedBatches += batch
        seenBatches[batch.batchId]?.let { return it.copy(rejected = emptyList(), replayed = true) }
        var accepted = 0
        var duplicates = 0
        val rejected = mutableListOf<RejectedPoint>()
        for (p in batch.points) {
            when {
                outsideWindow(p) -> rejected += RejectedPoint(p.clientPointId, "outside_shift")
                !storedPointIds.add(p.clientPointId) -> duplicates++
                else -> accepted++
            }
        }
        return PointBatchResult(batch.batchId, accepted, duplicates, rejected).also {
            seenBatches[batch.batchId] = it
        }
    }

    override suspend fun uploadEvents(request: TrackingEventsRequest): TrackingEventsResult {
        maybeFail()
        eventCalls += request.events
        if (request.events.any(rejectEvent)) {
            throw ApiError.Rejected(404, "not_found", "الوردية غير موجودة")
        }
        val fresh = request.events.count { storedEventIds.add(it.clientEventId) }
        return TrackingEventsResult(fresh, request.events.size - fresh)
    }

    override suspend fun endShift(shiftId: String, request: EndShiftRequest, idempotencyKey: String): Shift {
        maybeFail()
        endFailure?.let { throw it }
        endCalls += shiftId to idempotencyKey
        return shift(shiftId)
    }

    override suspend fun login(request: LoginRequest): LoginResponse = error("unused")
    override suspend fun logout() = error("unused")
    override suspend fun me(): DriverMe = error("unused")
    override suspend fun catalog(): DriverCatalog = error("unused")
    override suspend fun activeShift(): Shift? = error("unused")
    override suspend fun todayShifts(): List<Shift> = error("unused")
    override suspend fun startShift(request: StartShiftRequest, idempotencyKey: String): Shift = error("unused")
    override suspend fun startSession(shiftId: String, request: StartSessionRequest, idempotencyKey: String): Session =
        error("unused")
    override suspend fun endSession(sessionId: String): Session = error("unused")
    override suspend fun trackingStatus(): ServerTrackingStatus = error("unused")
    override suspend fun recordFuel(request: FuelEntryRequest, idempotencyKey: String): FuelEntry = error("unused")
    override suspend fun myFuel(): List<FuelEntry> = error("unused")
}

fun offline() = ApiError.Network(IOException("offline"))
