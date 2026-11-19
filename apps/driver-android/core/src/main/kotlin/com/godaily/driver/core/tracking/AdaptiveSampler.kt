package com.godaily.driver.core.tracking

import com.godaily.driver.core.geo.distanceMeters

/** How often to ask the OS for location while a shift is active. */
data class SamplingConfig(
    val intervalMillis: Long,
    /**
     * Let the OS deliver fixes in groups, up to this delay, to save power.
     * Kept below the "no recent fix" threshold (3 intervals) so batching
     * never looks like signal loss.
     */
    val maxDelayMillis: Long,
    val motion: Motion,
    val lowPower: Boolean,
)

enum class Motion { MOVING, STATIONARY }

data class PowerState(val batteryPercent: Int?, val charging: Boolean, val powerSaveMode: Boolean) {
    val constrained: Boolean
        get() = powerSaveMode || (!charging && batteryPercent != null && batteryPercent <= LOW_BATTERY)

    companion object {
        const val LOW_BATTERY = 15
        val UNKNOWN = PowerState(batteryPercent = null, charging = false, powerSaveMode = false)
    }
}

data class SamplingParams(
    val movingIntervalMillis: Long = 10_000,
    val stationaryIntervalMillis: Long = 60_000,
    /** Speed above which the vehicle counts as moving (≈ 11 km/h). */
    val movingSpeedMps: Float = 3f,
    /** Distance from the stationary anchor that counts as moving. */
    val movingDistanceM: Double = 75.0,
    /** No movement for this long switches to the stationary interval. */
    val stationaryAfterMillis: Long = 180_000,
    /** Fixes worse than this cannot tell movement from jitter. */
    val maxUsableAccuracyM: Float = 100f,
    val lowPowerFactor: Int = 2,
)

/**
 * Battery-conscious sampling for work-shift tracking.
 *
 * Moving vehicles are sampled often (route shape, geofences); a parked
 * vehicle is sampled slowly. Low battery or power-save mode doubles the
 * interval but never stops tracking: a shift must not lose its record
 * silently. The slowest interval (stationary + low power = 120 s) stays
 * well under the server's 300 s gap threshold, so a parked vehicle keeps
 * producing heartbeat points instead of looking like a tracking gap.
 *
 * Distance filtering is deliberately not used for the same reason.
 */
class AdaptiveSampler(private val params: SamplingParams = SamplingParams()) {
    private var motion = Motion.MOVING
    private var anchor: LocationFix? = null
    private var lastMovementAt: Long? = null
    private var power = PowerState.UNKNOWN

    var config: SamplingConfig = build()
        private set

    /** Returns the new config when it changed (the caller re-subscribes), else null. */
    fun onPowerChanged(state: PowerState): SamplingConfig? {
        power = state
        return update()
    }

    fun onFix(fix: LocationFix): SamplingConfig? {
        val accuracy = fix.accuracyM
        if (accuracy != null && accuracy > params.maxUsableAccuracyM) return null
        val start = anchor
        val speed = fix.speedMps
        val moved = (speed != null && speed >= params.movingSpeedMps) ||
            (start != null && distanceMeters(start.latitude, start.longitude, fix.latitude, fix.longitude) >
                params.movingDistanceM)
        if (start == null || moved) {
            anchor = fix
            lastMovementAt = fix.timeMillis
            motion = Motion.MOVING
        } else {
            val since = fix.timeMillis - (lastMovementAt ?: fix.timeMillis)
            if (since >= params.stationaryAfterMillis) motion = Motion.STATIONARY
        }
        return update()
    }

    private fun update(): SamplingConfig? {
        val next = build()
        if (next == config) return null
        config = next
        return next
    }

    private fun build(): SamplingConfig {
        val base = if (motion == Motion.MOVING) params.movingIntervalMillis else params.stationaryIntervalMillis
        val lowPower = power.constrained
        val interval = if (lowPower) base * params.lowPowerFactor else base
        return SamplingConfig(
            intervalMillis = interval,
            maxDelayMillis = interval * 2,
            motion = motion,
            lowPower = lowPower,
        )
    }
}
