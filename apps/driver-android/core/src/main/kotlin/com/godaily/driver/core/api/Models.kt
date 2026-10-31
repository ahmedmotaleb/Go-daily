package com.godaily.driver.core.api

import java.time.Instant
import java.time.LocalDate
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// Wire models for the Go Daily driver API (/api/v1). Field names mirror the
// server's Pydantic schemas (apps/api/app/schemas). Unknown fields are
// ignored so the server can add fields without breaking installed apps.

@Serializable
data class LoginRequest(
    val phone: String,
    val password: String,
    val client: String = "mobile",
    @SerialName("device_name") val deviceName: String? = null,
)

@Serializable
data class LoginResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("expires_at") @Serializable(InstantSerializer::class) val expiresAt: Instant,
    val user: UserSummary,
)

@Serializable
data class UserSummary(
    val id: String,
    @SerialName("full_name") val fullName: String,
    val role: String,
)

@Serializable
data class DriverVehicle(
    val id: String,
    @SerialName("internal_code") val internalCode: String,
    @SerialName("plate_number") val plateNumber: String,
    @SerialName("vehicle_type") val vehicleType: String,
    @SerialName("assignment_role") val assignmentRole: String,
    @SerialName("last_odometer_km") val lastOdometerKm: Int? = null,
)

@Serializable
data class DriverMe(
    @SerialName("driver_id") val driverId: String,
    @SerialName("full_name") val fullName: String,
    val phone: String,
    @SerialName("license_expiry") @Serializable(LocalDateSerializer::class)
    val licenseExpiry: LocalDate? = null,
    @SerialName("license_status") val licenseStatus: String,
    val vehicles: List<DriverVehicle>,
    @SerialName("active_shift") val activeShift: Shift? = null,
)

@Serializable
data class OperationType(
    val id: String,
    val code: String,
    val kind: String,
    @SerialName("name_ar") val nameAr: String,
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("uses_routes") val usesRoutes: Boolean = false,
)

@Serializable
data class DriverRoute(
    val id: String,
    val name: String,
    @SerialName("operation_type_id") val operationTypeId: String,
)

@Serializable
data class DriverFuelType(
    val id: String,
    val code: String,
    @SerialName("name_ar") val nameAr: String,
    @SerialName("default_unit") val defaultUnit: String,
)

@Serializable
data class DriverCatalog(
    @SerialName("operation_types") val operationTypes: List<OperationType>,
    val routes: List<DriverRoute>,
    @SerialName("fuel_types") val fuelTypes: List<DriverFuelType> = emptyList(),
)

/** Fuel/oil entry during the active shift. Money and quantities are decimal strings. */
@Serializable
data class FuelEntryRequest(
    @SerialName("fuel_type_id") val fuelTypeId: String,
    val quantity: String,
    @SerialName("total_amount") val totalAmount: String,
    @SerialName("odometer_km") val odometerKm: Int? = null,
    val vendor: String? = null,
    @SerialName("paid_by") val paidBy: String = "DRIVER",
    @SerialName("payment_method") val paymentMethod: String = "CASH",
    val notes: String? = null,
    /** Where the phone was when the entry was made (latest in-shift fix), if recent. */
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerialName("location_accuracy_m") val locationAccuracyM: Double? = null,
)

@Serializable
data class UploadedAttachment(val id: String)

/** Answer to a receipt upload; `duplicates` lists earlier files with identical bytes. */
@Serializable
data class ReceiptUploadResult(
    val attachment: UploadedAttachment,
    val duplicates: List<kotlinx.serialization.json.JsonObject> = emptyList(),
) {
    val possibleDuplicate: Boolean get() = duplicates.isNotEmpty()
}

@Serializable
data class FuelEntry(
    val id: String,
    @SerialName("fuel_type") val fuelType: String,
    val quantity: String,
    val unit: String,
    @SerialName("total_amount") val totalAmount: String,
    @SerialName("occurred_at") @Serializable(InstantSerializer::class) val occurredAt: Instant,
    val status: String,
    @SerialName("paid_by") val paidBy: String,
)

@Serializable
data class VehicleRef(
    val id: String,
    @SerialName("internal_code") val internalCode: String,
    @SerialName("plate_number") val plateNumber: String,
)

@Serializable
data class OperationTypeRef(
    val id: String,
    val code: String,
    val kind: String,
    @SerialName("name_ar") val nameAr: String,
)

@Serializable
data class RouteRef(val id: String, val name: String)

@Serializable
data class Session(
    val id: String,
    @SerialName("shift_id") val shiftId: String,
    @SerialName("operation_type") val operationType: OperationTypeRef,
    val route: RouteRef? = null,
    val status: String,
    @SerialName("started_at") @Serializable(InstantSerializer::class) val startedAt: Instant,
    @SerialName("ended_at") @Serializable(InstantSerializer::class) val endedAt: Instant? = null,
    val loops: Int = 0,
    val legs: Int = 0,
)

@Serializable
data class Shift(
    val id: String,
    val vehicle: VehicleRef,
    val status: String,
    @SerialName("planned_start_at") @Serializable(InstantSerializer::class)
    val plannedStartAt: Instant? = null,
    @SerialName("planned_operation_type") val plannedOperationType: OperationTypeRef? = null,
    @SerialName("planned_route") val plannedRoute: RouteRef? = null,
    @SerialName("started_at") @Serializable(InstantSerializer::class) val startedAt: Instant? = null,
    @SerialName("ended_at") @Serializable(InstantSerializer::class) val endedAt: Instant? = null,
    @SerialName("start_odometer_km") val startOdometerKm: Int? = null,
    @SerialName("end_odometer_km") val endOdometerKm: Int? = null,
    @SerialName("duration_minutes") val durationMinutes: Int? = null,
    val sessions: List<Session> = emptyList(),
    @SerialName("active_session") val activeSession: Session? = null,
) {
    val isActive: Boolean get() = status == "ACTIVE"
    val isPlanned: Boolean get() = status == "PLANNED"
}

@Serializable
data class StartShiftRequest(
    @SerialName("vehicle_id") val vehicleId: String,
    @SerialName("start_odometer_km") val startOdometerKm: Int,
    @SerialName("planned_shift_id") val plannedShiftId: String? = null,
    @SerialName("operation_type_id") val operationTypeId: String? = null,
    @SerialName("route_id") val routeId: String? = null,
)

@Serializable
data class EndShiftRequest(
    @SerialName("end_odometer_km") val endOdometerKm: Int,
    val notes: String? = null,
)

@Serializable
data class StartSessionRequest(
    @SerialName("operation_type_id") val operationTypeId: String,
    @SerialName("route_id") val routeId: String? = null,
)

/** Location sources accepted by the server (PointSource). */
enum class PointSource { GPS, NETWORK, FUSED, UNKNOWN }

@Serializable
data class GpsPoint(
    @SerialName("client_point_id") val clientPointId: String,
    @SerialName("recorded_at") @Serializable(InstantSerializer::class) val recordedAt: Instant,
    val latitude: Double,
    val longitude: Double,
    @SerialName("accuracy_m") val accuracyM: Double? = null,
    @SerialName("speed_mps") val speedMps: Double? = null,
    @SerialName("heading_deg") val headingDeg: Double? = null,
    @SerialName("altitude_m") val altitudeM: Double? = null,
    val source: PointSource = PointSource.UNKNOWN,
    @SerialName("is_mock") val isMock: Boolean = false,
)

@Serializable
data class DeviceInfo(
    @SerialName("app_version") val appVersion: String? = null,
    @SerialName("battery_level") val batteryLevel: Int? = null,
    @SerialName("pending_points") val pendingPoints: Int? = null,
)

@Serializable
data class PointBatch(
    @SerialName("batch_id") val batchId: String,
    @SerialName("shift_id") val shiftId: String,
    val points: List<GpsPoint>,
    val device: DeviceInfo? = null,
) {
    companion object {
        /** Server-side limit (PointBatchIn.points max_length). */
        const val MAX_POINTS = 500
    }
}

@Serializable
data class RejectedPoint(
    @SerialName("client_point_id") val clientPointId: String,
    val reason: String,
)

@Serializable
data class PointBatchResult(
    @SerialName("batch_id") val batchId: String,
    val accepted: Int,
    val duplicates: Int,
    val rejected: List<RejectedPoint> = emptyList(),
    val replayed: Boolean = false,
)

/** Device-side tracking events (server TrackingEventType). */
enum class TrackingEventType {
    TRACKING_STARTED,
    TRACKING_STOPPED,
    PERMISSION_GRANTED,
    PERMISSION_DENIED,
    BACKGROUND_PERMISSION_DENIED,
    LOCATION_DISABLED,
    LOCATION_ENABLED,
    GPS_SIGNAL_LOST,
    GPS_SIGNAL_RESTORED,
    BATTERY_OPTIMIZATION_ENABLED,
    SERVICE_RESTARTED,
    OFFLINE_QUEUE_BACKLOG,
}

@Serializable
data class TrackingEvent(
    @SerialName("client_event_id") val clientEventId: String,
    @SerialName("event_type") val eventType: TrackingEventType,
    @SerialName("occurred_at") @Serializable(InstantSerializer::class) val occurredAt: Instant,
    @SerialName("shift_id") val shiftId: String? = null,
    val details: JsonObject? = null,
)

@Serializable
data class TrackingEventsRequest(val events: List<TrackingEvent>) {
    companion object {
        /** Server-side limit (TrackingEventsIn.events max_length). */
        const val MAX_EVENTS = 200
    }
}

@Serializable
data class TrackingEventsResult(val accepted: Int, val duplicates: Int)

@Serializable
data class ServerTrackingStatus(
    @SerialName("shift_id") val shiftId: String? = null,
    val state: String,
    @SerialName("last_point_recorded_at") @Serializable(InstantSerializer::class)
    val lastPointRecordedAt: Instant? = null,
    @SerialName("last_point_received_at") @Serializable(InstantSerializer::class)
    val lastPointReceivedAt: Instant? = null,
)
