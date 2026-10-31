package com.godaily.driver.core.tracking

import com.godaily.driver.core.api.GpsPoint
import com.godaily.driver.core.api.PointSource
import java.time.Instant

/** A platform location fix, as delivered by the OS (no Android types). */
data class LocationFix(
    val timeMillis: Long,
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Float? = null,
    val speedMps: Float? = null,
    val bearingDeg: Float? = null,
    val altitudeM: Double? = null,
    val provider: String? = null,
    val isMock: Boolean = false,
)

private fun Double?.within(min: Double, max: Double): Double? =
    this?.takeIf { !it.isNaN() && it in min..max }

private fun Float?.within(min: Double, max: Double): Double? = this?.toDouble().within(min, max)

/**
 * Maps a fix to the upload model, applying the server's field bounds.
 *
 * Optional measurements outside the accepted range are dropped (sent as
 * null) so one odd sensor value cannot make the server reject a whole
 * batch. Coordinates are never altered: a fix with impossible coordinates
 * is discarded (returns null) instead of being "corrected".
 */
fun LocationFix.toGpsPoint(clientPointId: String): GpsPoint? {
    if (latitude.isNaN() || longitude.isNaN()) return null
    if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) return null
    if (latitude == 0.0 && longitude == 0.0) return null // "null island": no real fix
    return GpsPoint(
        clientPointId = clientPointId,
        recordedAt = Instant.ofEpochMilli(timeMillis),
        latitude = latitude,
        longitude = longitude,
        accuracyM = accuracyM.within(0.0, 100_000.0),
        speedMps = speedMps.within(0.0, 200.0),
        headingDeg = bearingDeg.within(0.0, 360.0),
        altitudeM = altitudeM.within(-500.0, 10_000.0),
        source = when (provider?.lowercase()) {
            "gps" -> PointSource.GPS
            "network" -> PointSource.NETWORK
            "fused" -> PointSource.FUSED
            else -> PointSource.UNKNOWN
        },
        isMock = isMock,
    )
}

/**
 * Drops repeated or out-of-order fixes (same or older timestamp than the
 * last one kept). Location providers occasionally redeliver a cached fix;
 * keeping it would only add a duplicate point. Nothing is ever invented.
 */
class FixDeduplicator {
    private var lastTime: Long? = null

    fun accept(fix: LocationFix): Boolean {
        val last = lastTime
        if (last != null && fix.timeMillis <= last) return false
        lastTime = fix.timeMillis
        return true
    }
}

/** The latest fix the tracking service recorded, kept in memory only. */
data class LastPosition(
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double?,
    val atMillis: Long,
) {
    /**
     * This position if it is recent enough to describe where the phone is
     * now (e.g. at the fuel station); otherwise null. Nothing is guessed.
     */
    fun freshAt(nowMillis: Long, maxAgeMillis: Long = MAX_AGE_MILLIS): LastPosition? =
        takeIf { nowMillis - atMillis in 0..maxAgeMillis }

    companion object {
        const val MAX_AGE_MILLIS = 120_000L
    }
}
