package com.godaily.driver.core.api

import java.time.Instant
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

private const val SHIFT_JSON = """
{
  "id": "0b6c7f1e-2a51-4c9a-9d5b-1f0e1c2d3e4f",
  "driver": {"id": "d1", "full_name": "سائق"},
  "vehicle": {"id": "v1", "internal_code": "MB-01", "plate_number": "ق ط ر 123"},
  "status": "ACTIVE",
  "source": "DRIVER_APP",
  "planned_start_at": null,
  "planned_operation_type": null,
  "planned_route": null,
  "started_at": "2026-03-01T06:30:00.123456Z",
  "ended_at": null,
  "start_odometer_km": 120450,
  "end_odometer_km": null,
  "odometer_distance_km": null,
  "duration_minutes": 12,
  "sessions": [],
  "active_session": {
    "id": "se1", "shift_id": "0b6c7f1e-2a51-4c9a-9d5b-1f0e1c2d3e4f",
    "operation_type": {"id": "o1", "code": "FIXED_ROUTE", "kind": "FIXED_ROUTE", "name_ar": "خط ثابت"},
    "route": {"id": "r1", "name": "المحطة - الجامعة"},
    "status": "ACTIVE", "started_at": "2026-03-01T08:30:00+02:00", "ended_at": null,
    "start_odometer_km": null, "end_odometer_km": null, "notes": null, "loops": 2, "legs": 5
  },
  "created_at": "2026-03-01T06:30:00Z",
  "updated_at": "2026-03-01T06:30:00Z",
  "some_future_field": {"nested": true}
}
"""

class OkHttpDriverApiTest {
    private lateinit var server: MockWebServer
    private lateinit var api: OkHttpDriverApi
    private var token: String? = "gd_test-token"

    @BeforeEach
    fun setUp() {
        server = MockWebServer()
        server.start()
        val client = OkHttpClient.Builder().readTimeout(2, TimeUnit.SECONDS).build()
        api = OkHttpDriverApi(server.url("/api/v1").toString(), { token }, client, io = Dispatchers.Unconfined)
    }

    @AfterEach
    fun tearDown() {
        server.close()
    }

    private fun respond(code: Int, body: String) {
        server.enqueue(MockResponse.Builder().code(code).body(body).addHeader("Content-Type", "application/json").build())
    }

    @Test
    fun `login posts a mobile client login without a bearer token`() = runTest {
        respond(
            200,
            """{"access_token":"gd_new","token_type":"bearer","expires_at":"2026-04-01T00:00:00Z",
               "user":{"id":"u1","full_name":"سائق","role":"DRIVER","phone":"+201000000000","permissions":[]}}""",
        )
        token = null
        val res = api.login(LoginRequest(phone = "01000000000", password = "secret", deviceName = "Pixel"))
        assertEquals("gd_new", res.accessToken)
        assertEquals(Instant.parse("2026-04-01T00:00:00Z"), res.expiresAt)

        val req = server.takeRequest()
        assertEquals("/api/v1/auth/login", req.url.encodedPath)
        assertNull(req.headers["Authorization"])
        val body = GoDailyJson.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals("mobile", body["client"]!!.jsonPrimitive.content)
        assertEquals("Pixel", body["device_name"]!!.jsonPrimitive.content)
    }

    @Test
    fun `shift responses parse, tolerating new fields and offsets`() = runTest {
        respond(200, SHIFT_JSON)
        val shift = api.activeShift()!!
        assertTrue(shift.isActive)
        assertEquals("MB-01", shift.vehicle.internalCode)
        assertEquals(2, shift.activeSession!!.loops)
        assertEquals(Instant.parse("2026-03-01T06:30:00Z"), shift.activeSession.startedAt)
        assertEquals("Bearer gd_test-token", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun `no active shift is null`() = runTest {
        respond(200, "null")
        assertNull(api.activeShift())
    }

    @Test
    fun `writes carry the idempotency key`() = runTest {
        respond(201, SHIFT_JSON)
        api.startShift(StartShiftRequest(vehicleId = "v1", startOdometerKm = 120450), "key-123")
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/api/v1/driver/shifts/start", req.url.encodedPath)
        assertEquals("key-123", req.headers["Idempotency-Key"])
        val body = GoDailyJson.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals(120450, body["start_odometer_km"]!!.jsonPrimitive.content.toInt())
        assertTrue("planned_shift_id" !in body) // nulls are omitted
    }

    @Test
    fun `point batches use the server's field names`() = runTest {
        respond(200, """{"batch_id":"b1","accepted":1,"duplicates":0,"rejected":[],"replayed":false}""")
        val point = GpsPoint(
            clientPointId = "p1",
            recordedAt = Instant.parse("2026-03-01T06:30:00Z"),
            latitude = 31.04,
            longitude = 31.37,
            accuracyM = 8.0,
            source = PointSource.FUSED,
        )
        val result = api.uploadPoints(PointBatch("b1", "s1", listOf(point), DeviceInfo("1.0", 80, 1)))
        assertEquals(1, result.accepted)
        val body = GoDailyJson.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        val sent = body["points"]!!.toString()
        assertTrue("\"client_point_id\":\"p1\"" in sent)
        assertTrue("\"recorded_at\":\"2026-03-01T06:30:00Z\"" in sent)
        assertTrue("\"source\":\"FUSED\"" in sent)
        assertTrue("\"is_mock\":false" in sent)
        assertEquals("80", body["device"]!!.jsonObject["battery_level"]!!.jsonPrimitive.content)
    }

    @Test
    fun `401 means log in again`() = runTest {
        respond(401, """{"error":{"code":"invalid_token","message":"انتهت الجلسة"}}""")
        val e = assertThrows<ApiError.Unauthorized> { api.me() }
        assertEquals("invalid_token", e.code)
        assertEquals("انتهت الجلسة", e.message)
    }

    @Test
    fun `validation errors keep the Arabic message and field errors`() = runTest {
        respond(
            422,
            """{"error":{"code":"validation_error","message":"البيانات المدخلة غير صحيحة",
               "details":{"fields":[{"loc":["body","start_odometer_km"],"msg":"too large","type":"x"}]}}}""",
        )
        val e = assertThrows<ApiError.Rejected> {
            api.startShift(StartShiftRequest(vehicleId = "v1", startOdometerKm = 1), "k")
        }
        assertEquals(422, e.status)
        assertEquals(mapOf("start_odometer_km" to "too large"), e.fieldErrors)
        assertTrue(!e.retryable)
    }

    @Test
    fun `server errors and throttling are retryable`() = runTest {
        respond(503, "<html>maintenance</html>")
        val e = assertThrows<ApiError.Server> { api.me() }
        assertEquals(503, e.status)
        assertTrue(e.retryable)
        respond(429, """{"error":{"code":"rate_limited","message":"محاولات كثيرة"}}""")
        assertEquals("rate_limited", assertThrows<ApiError.Server> { api.me() }.code)
    }

    @Test
    fun `an unexpected 200 page (captive portal) is treated as no connection`() = runTest {
        respond(200, "<html>Login to Wi-Fi</html>")
        assertThrows<ApiError.Network> { api.me() }
    }

    @Test
    fun `an unreachable server is a network error`() = runTest {
        server.close()
        val e = assertThrows<ApiError.Network> { api.trackingStatus() }
        assertTrue(e.retryable)
    }

    @Test
    fun `ids are not allowed to alter the request path`() = runTest {
        assertThrows<IllegalArgumentException> { api.endSession("../auth/logout") }
    }

    @Test
    fun `fuel entries send decimal strings and the idempotency key`() = runTest {
        respond(
            201,
            """{"id":"f1","fuel_type":"غاز طبيعي","quantity":"12.000","unit":"CUBIC_METER",
               "total_amount":"84.00","occurred_at":"2026-03-01T06:30:00Z","status":"SUBMITTED","paid_by":"DRIVER"}""",
        )
        val entry = api.recordFuel(FuelEntryRequest(fuelTypeId = "t1", quantity = "12", totalAmount = "84.00"), "fuel-1")
        assertEquals("84.00", entry.totalAmount)
        assertEquals("SUBMITTED", entry.status)
        val req = server.takeRequest()
        assertEquals("/api/v1/driver/fuel", req.url.encodedPath)
        assertEquals("fuel-1", req.headers["Idempotency-Key"])
        val body = GoDailyJson.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertTrue(body["total_amount"]!!.jsonPrimitive.isString) // never a float
        assertEquals("DRIVER", body["paid_by"]!!.jsonPrimitive.content)
    }

    @Test
    fun `fuel entries carry the phone's position only when one is given`() = runTest {
        val entryJson = """{"id":"f2","fuel_type":"بنزين","quantity":"20.000","unit":"LITER",
            "total_amount":"300.00","occurred_at":"2026-03-01T06:30:00Z","status":"SUBMITTED","paid_by":"DRIVER"}"""
        respond(201, entryJson)
        api.recordFuel(
            FuelEntryRequest(
                fuelTypeId = "t2", quantity = "20", totalAmount = "300",
                latitude = 30.0444, longitude = 31.2357, locationAccuracyM = 12.0,
            ),
            "fuel-2",
        )
        val withPosition = GoDailyJson.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("30.0444", withPosition["latitude"]!!.jsonPrimitive.content)
        assertEquals("12.0", withPosition["location_accuracy_m"]!!.jsonPrimitive.content)

        respond(201, entryJson)
        api.recordFuel(FuelEntryRequest(fuelTypeId = "t2", quantity = "20", totalAmount = "300"), "fuel-3")
        val without = GoDailyJson.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertTrue("latitude" !in without && "longitude" !in without) // omitted, not invented
    }

    @Test
    fun `receipt photos are uploaded as multipart to the entry`() = runTest {
        respond(
            201,
            """{"attachment":{"id":"a1","kind":"FUEL_RECEIPT","content_type":"image/jpeg","size_bytes":4},
               "duplicates":[{"id":"a0","owner_type":"fuel_transaction"}]}""",
        )
        val result = api.uploadFuelReceipt("f1", byteArrayOf(1, 2, 3, 4))
        assertEquals("a1", result.attachment.id)
        assertTrue(result.possibleDuplicate)
        val req = server.takeRequest()
        assertEquals("/api/v1/driver/fuel/f1/receipt", req.url.encodedPath)
        assertEquals("Bearer gd_test-token", req.headers["Authorization"])
        assertTrue(req.headers["Content-Type"]!!.startsWith("multipart/form-data"))
        val body = req.body!!.utf8()
        assertTrue("name=\"file\"; filename=\"receipt.jpg\"" in body)
        assertTrue("Content-Type: image/jpeg" in body)
        assertThrows<IllegalArgumentException> { api.uploadFuelReceipt("../../users", byteArrayOf(1)) }
    }

    @Test
    fun `catalog includes fuel types and tolerates older servers without them`() = runTest {
        respond(
            200,
            """{"operation_types":[],"routes":[],
               "fuel_types":[{"id":"t1","code":"CNG","name_ar":"غاز طبيعي","default_unit":"CUBIC_METER"}]}""",
        )
        assertEquals("CNG", api.catalog().fuelTypes.single().code)
        respond(200, """{"operation_types":[],"routes":[]}""")
        assertTrue(api.catalog().fuelTypes.isEmpty())
    }
}
