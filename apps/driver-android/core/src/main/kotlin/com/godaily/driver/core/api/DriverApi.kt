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

    suspend fun recordFuel(request: FuelEntryRequest, idempotencyKey: String): FuelEntry

    suspend fun myFuel(): List<FuelEntry>

    /** Photo of the receipt for one of the driver's own fuel entries (JPEG, PNG or WebP). */
    suspend fun uploadFuelReceipt(entryId: String, image: ByteArray, contentType: String = "image/jpeg"): ReceiptUploadResult

    suspend fun uploadPoints(batch: PointBatch): PointBatchResult

    suspend fun uploadEvents(request: TrackingEventsRequest): TrackingEventsResult

    suspend fun trackingStatus(): ServerTrackingStatus

    /** Today's day-off, if registered. */
    suspend fun todayDayOff(): DayOff?

    suspend fun registerDayOff(request: DayOffRequest, idempotencyKey: String): DayOff

    suspend fun cancelDayOff(): DayOff

    /** Odometer photo for the next shift start; returns the id to send with the start. */
    suspend fun uploadOdometerPhoto(image: ByteArray, contentType: String = "image/jpeg"): PhotoUpload

    /** Ends the shift (if still running) and records the day's money in one step. */
    suspend fun submitCloseout(shiftId: String, request: CloseoutRequest, idempotencyKey: String): Closeout

    suspend fun uploadCloseoutReceipt(
        closeoutId: String,
        image: ByteArray,
        contentType: String = "image/jpeg",
    ): PhotoUpload

    suspend fun account(): CashAccount
}

/** Supplies the current bearer token; null when logged out. */
fun interface TokenProvider {
    fun token(): String?
}
