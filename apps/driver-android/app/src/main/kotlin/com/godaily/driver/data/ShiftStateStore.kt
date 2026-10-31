package com.godaily.driver.data

import android.content.Context
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.sync.PendingShiftEnd
import com.godaily.driver.core.sync.PendingShiftEndStore
import com.godaily.driver.core.tracking.TrackingIssue
import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Local work context: which shift (if any) authorises tracking right now.
 *
 * Tracking runs only while [activeShiftId] is set. It is set when the
 * server confirms a started shift and cleared the moment the driver ends
 * the shift (even before the server hears about it) or when the server
 * reports that the shift is no longer active.
 */
class ShiftStateStore(context: Context) : PendingShiftEndStore {
    private val prefs = context.getSharedPreferences("gd_shift", Context.MODE_PRIVATE)
    private val _version = MutableStateFlow(0)

    /** Bumps on every change so observers can re-read. */
    val version: StateFlow<Int> = _version

    val activeShiftId: String? get() = prefs.getString(ACTIVE_ID, null)

    val activeVehicleCode: String? get() = prefs.getString(ACTIVE_VEHICLE, null)

    var disclosureAccepted: Boolean
        get() = prefs.getBoolean(DISCLOSURE, false)
        set(value) = edit { putBoolean(DISCLOSURE, value) }

    var lastSyncAtMillis: Long
        get() = prefs.getLong(LAST_SYNC, 0L)
        set(value) = edit { putLong(LAST_SYNC, value) }

    var lastShiftEndError: String?
        get() = prefs.getString(END_ERROR, null)
        set(value) = edit { putString(END_ERROR, value) }

    fun setActive(shift: Shift) = edit {
        putString(ACTIVE_ID, shift.id)
        putString(ACTIVE_VEHICLE, shift.vehicle.internalCode)
    }

    fun clearActive() = edit {
        remove(ACTIVE_ID)
        remove(ACTIVE_VEHICLE)
        remove(REPORTED_SHIFT)
        remove(REPORTED_ISSUES)
    }

    /** True the first time tracking starts for [shiftId]; later starts are restarts. */
    fun markTrackingStarted(shiftId: String): Boolean {
        if (prefs.getString(TRACKING_SHIFT, null) == shiftId) return false
        edit { putString(TRACKING_SHIFT, shiftId) }
        return true
    }

    fun reportedIssues(shiftId: String?): Set<TrackingIssue>? {
        if (shiftId == null || prefs.getString(REPORTED_SHIFT, null) != shiftId) return null
        return prefs.getStringSet(REPORTED_ISSUES, emptySet()).orEmpty()
            .mapNotNull { name -> TrackingIssue.entries.firstOrNull { it.name == name } }
            .toSet()
    }

    fun saveReportedIssues(shiftId: String, issues: Set<TrackingIssue>) = edit {
        putString(REPORTED_SHIFT, shiftId)
        putStringSet(REPORTED_ISSUES, issues.map { it.name }.toSet())
    }

    val pendingEndShiftId: String? get() = prefs.getString(END_SHIFT, null)

    fun savePendingEnd(end: PendingShiftEnd) = edit {
        putString(END_SHIFT, end.shiftId)
        putInt(END_ODOMETER, end.endOdometerKm)
        putString(END_NOTES, end.notes)
        putString(END_KEY, end.idempotencyKey)
        putLong(END_AT, end.requestedAt.toEpochMilli())
        remove(END_ERROR)
    }

    override suspend fun get(): PendingShiftEnd? {
        val shiftId = prefs.getString(END_SHIFT, null) ?: return null
        return PendingShiftEnd(
            shiftId = shiftId,
            endOdometerKm = prefs.getInt(END_ODOMETER, 0),
            notes = prefs.getString(END_NOTES, null),
            idempotencyKey = prefs.getString(END_KEY, null) ?: return null,
            requestedAt = Instant.ofEpochMilli(prefs.getLong(END_AT, 0L)),
        )
    }

    override suspend fun clear() = edit {
        remove(END_SHIFT)
        remove(END_ODOMETER)
        remove(END_NOTES)
        remove(END_KEY)
        remove(END_AT)
    }

    private inline fun edit(block: android.content.SharedPreferences.Editor.() -> Unit) {
        // commit(): the work context must be on disk before tracking reacts to it.
        prefs.edit().apply(block).commit()
        _version.value += 1
    }

    private companion object {
        const val ACTIVE_ID = "active_shift_id"
        const val ACTIVE_VEHICLE = "active_vehicle"
        const val TRACKING_SHIFT = "tracking_started_for"
        const val REPORTED_SHIFT = "reported_shift"
        const val REPORTED_ISSUES = "reported_issues"
        const val DISCLOSURE = "disclosure_accepted"
        const val LAST_SYNC = "last_sync_at"
        const val END_SHIFT = "pending_end_shift"
        const val END_ODOMETER = "pending_end_odometer"
        const val END_NOTES = "pending_end_notes"
        const val END_KEY = "pending_end_key"
        const val END_AT = "pending_end_at"
        const val END_ERROR = "end_error"
    }
}
