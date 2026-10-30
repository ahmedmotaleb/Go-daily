package com.godaily.driver.core.api

/**
 * The driver-facing API. All calls throw [ApiError] on failure.
 *
 * Writes that create or change server state take an idempotency key: the
 * caller must generate it once per user intent and reuse it on retries so a
 * retried request never starts two shifts or ends one twice.
 */
interface DriverApi {
    suspend fun login(request: LoginRequest): LoginResponse

    suspend fun logout()

    suspend fun me(): DriverMe

    suspend fun catalog(): DriverCatalog

    suspend fun activeShift(): Shift?

    suspend fun todayShifts(): List<Shift>

    suspend fun startShift(request: StartShiftRequest, idempotencyKey: String): Shift

    suspend fun endShift(shiftId: String, request: EndShiftRequest, idempotencyKey: String): Shift

    suspend fun startSession(shiftId: String, request: StartSessionRequest, idempotencyKey: String): Session

    suspend fun endSession(sessionId: String): Session

    suspend fun uploadPoints(batch: PointBatch): PointBatchResult

    suspend fun uploadEvents(request: TrackingEventsRequest): TrackingEventsResult

    suspend fun trackingStatus(): ServerTrackingStatus
}

/** Supplies the current bearer token; null when logged out. */
fun interface TokenProvider {
    fun token(): String?
}
