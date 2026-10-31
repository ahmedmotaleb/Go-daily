package com.godaily.driver.core.api

import java.io.IOException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.nullable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

/**
 * [DriverApi] over OkHttp.
 *
 * Never logs request or response bodies: they carry the bearer token,
 * passwords and the driver's location.
 */
class OkHttpDriverApi(
    baseUrl: String,
    private val tokens: TokenProvider,
    private val client: OkHttpClient,
    private val userAgent: String = "GoDailyDriver",
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : DriverApi {
    private val base: HttpUrl = baseUrl.trimEnd('/').plus("/").toHttpUrl()

    override suspend fun login(request: LoginRequest): LoginResponse =
        post("auth/login", request, LoginRequest.serializer(), LoginResponse.serializer(), auth = false)

    override suspend fun logout() {
        execute(build("auth/logout").post(EMPTY_BODY)) { }
    }

    override suspend fun me(): DriverMe = get("driver/me", DriverMe.serializer())

    override suspend fun catalog(): DriverCatalog = get("driver/catalog", DriverCatalog.serializer())

    override suspend fun activeShift(): Shift? = get("driver/shifts/active", Shift.serializer().nullable)

    override suspend fun todayShifts(): List<Shift> =
        get("driver/shifts/today", ListSerializer(Shift.serializer()))

    override suspend fun startShift(request: StartShiftRequest, idempotencyKey: String): Shift =
        post(
            "driver/shifts/start",
            request,
            StartShiftRequest.serializer(),
            Shift.serializer(),
            idempotencyKey = idempotencyKey,
        )

    override suspend fun endShift(
        shiftId: String,
        request: EndShiftRequest,
        idempotencyKey: String,
    ): Shift =
        post(
            "driver/shifts/${segment(shiftId)}/end",
            request,
            EndShiftRequest.serializer(),
            Shift.serializer(),
            idempotencyKey = idempotencyKey,
        )

    override suspend fun startSession(
        shiftId: String,
        request: StartSessionRequest,
        idempotencyKey: String,
    ): Session =
        post(
            "driver/shifts/${segment(shiftId)}/sessions",
            request,
            StartSessionRequest.serializer(),
            Session.serializer(),
            idempotencyKey = idempotencyKey,
        )

    override suspend fun endSession(sessionId: String): Session =
        execute(build("driver/sessions/${segment(sessionId)}/end").post(EMPTY_BODY)) {
            decode(it, Session.serializer())
        }

    override suspend fun recordFuel(request: FuelEntryRequest, idempotencyKey: String): FuelEntry =
        post(
            "driver/fuel",
            request,
            FuelEntryRequest.serializer(),
            FuelEntry.serializer(),
            idempotencyKey = idempotencyKey,
        )

    override suspend fun myFuel(): List<FuelEntry> = get("driver/fuel", ListSerializer(FuelEntry.serializer()))

    override suspend fun uploadFuelReceipt(
        entryId: String,
        image: ByteArray,
        contentType: String,
    ): ReceiptUploadResult {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", "receipt.${extensionFor(contentType)}", image.toRequestBody(contentType.toMediaType()))
            .build()
        return execute(build("driver/fuel/${segment(entryId)}/receipt").post(body)) {
            decode(it, ReceiptUploadResult.serializer())
        }
    }

    private fun extensionFor(contentType: String) = when (contentType) {
        "image/png" -> "png"
        "image/webp" -> "webp"
        else -> "jpg"
    }

    override suspend fun uploadPoints(batch: PointBatch): PointBatchResult =
        post("driver/tracking/points", batch, PointBatch.serializer(), PointBatchResult.serializer())

    override suspend fun uploadEvents(request: TrackingEventsRequest): TrackingEventsResult =
        post(
            "driver/tracking/events",
            request,
            TrackingEventsRequest.serializer(),
            TrackingEventsResult.serializer(),
        )

    override suspend fun trackingStatus(): ServerTrackingStatus =
        get("driver/tracking/status", ServerTrackingStatus.serializer())

    private suspend fun <T> get(path: String, serializer: KSerializer<T>): T =
        execute(build(path).get()) { decode(it, serializer) }

    private suspend fun <B, T> post(
        path: String,
        body: B,
        bodySerializer: KSerializer<B>,
        serializer: KSerializer<T>,
        auth: Boolean = true,
        idempotencyKey: String? = null,
    ): T {
        val json = GoDailyJson.encodeToString(bodySerializer, body).toRequestBody(JSON)
        val builder = build(path, auth).post(json)
        if (idempotencyKey != null) builder.header("Idempotency-Key", idempotencyKey)
        return execute(builder) { decode(it, serializer) }
    }

    private fun build(path: String, auth: Boolean = true): Request.Builder {
        val url = base.resolve(path) ?: throw IllegalArgumentException("bad path")
        val builder = Request.Builder().url(url).header("Accept", "application/json")
            .header("User-Agent", userAgent)
        if (auth) {
            tokens.token()?.let { builder.header("Authorization", "Bearer $it") }
        }
        return builder
    }

    private suspend fun <T> execute(builder: Request.Builder, read: (String) -> T): T =
        withContext(io) {
            val response = try {
                client.newCall(builder.build()).execute()
            } catch (e: IOException) {
                throw ApiError.Network(e)
            }
            response.use { handle(it, read) }
        }

    private fun <T> handle(response: Response, read: (String) -> T): T {
        val text = try {
            response.body.string()
        } catch (e: IOException) {
            throw ApiError.Network(e)
        }
        if (response.isSuccessful) return read(text)
        throw errorFor(response.code, text)
    }

    private fun <T> decode(text: String, serializer: KSerializer<T>): T = try {
        GoDailyJson.decodeFromString(serializer, text)
    } catch (e: IllegalArgumentException) {
        // A 2xx that is not the expected JSON (captive portal, proxy page).
        throw ApiError.Network(IOException("unexpected response body", e))
    }

    private fun segment(id: String): String {
        require(id.isNotBlank() && id.all { it.isLetterOrDigit() || it == '-' }) { "invalid id" }
        return id
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
        private val EMPTY_BODY: RequestBody = ByteArray(0).toRequestBody(null)

        internal fun errorFor(status: Int, body: String): ApiError {
            val error = parseEnvelope(body)
            val code = error?.get("code")?.jsonPrimitive?.contentOrNull ?: "http_$status"
            val message = error?.get("message")?.jsonPrimitive?.contentOrNull
                ?: "حدث خطأ غير متوقع ($status)"
            return when {
                status == 401 -> ApiError.Unauthorized(code, message)
                status == 429 || status >= 500 -> ApiError.Server(status, code, message)
                else -> ApiError.Rejected(status, code, message, fieldErrors(error))
            }
        }

        private fun parseEnvelope(body: String): JsonObject? = try {
            GoDailyJson.parseToJsonElement(body).jsonObject["error"]?.jsonObject
        } catch (_: IllegalArgumentException) {
            null
        }

        private fun fieldErrors(error: JsonObject?): Map<String, String> {
            val fields = (error?.get("details") as? JsonObject)?.get("fields") as? JsonArray
                ?: return emptyMap()
            return fields.mapNotNull { item: JsonElement ->
                val obj = item as? JsonObject ?: return@mapNotNull null
                val field = obj["loc"]?.jsonArray?.lastOrNull()?.jsonPrimitive?.contentOrNull
                val msg = obj["msg"]?.jsonPrimitive?.contentOrNull
                if (field != null && msg != null) field to msg else null
            }.toMap()
        }
    }
}
