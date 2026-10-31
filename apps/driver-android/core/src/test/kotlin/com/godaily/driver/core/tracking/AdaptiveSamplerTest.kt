package com.godaily.driver.core.tracking

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class AdaptiveSamplerTest {
    private fun fix(t: Long, lon: Double = 31.37, speed: Float? = 0f, accuracy: Float = 8f) =
        LocationFix(timeMillis = t, latitude = 31.04, longitude = lon, accuracyM = accuracy, speedMps = speed)

    @Test
    fun `starts at the moving interval`() {
        val sampler = AdaptiveSampler()
        assertEquals(Motion.MOVING, sampler.config.motion)
        assertEquals(10_000, sampler.config.intervalMillis)
    }

    @Test
    fun `slows down only after three minutes without movement`() {
        val sampler = AdaptiveSampler()
        assertNull(sampler.onFix(fix(0)))
        assertNull(sampler.onFix(fix(170_000)))
        val parked = sampler.onFix(fix(180_000))
        assertNotNull(parked)
        assertEquals(Motion.STATIONARY, parked!!.motion)
        assertEquals(60_000, parked.intervalMillis)
    }

    @Test
    fun `GPS jitter while parked does not count as movement`() {
        val sampler = AdaptiveSampler()
        sampler.onFix(fix(0))
        // ±0.0003° of longitude ≈ 30 m: noise around a parked vehicle.
        sampler.onFix(fix(60_000, lon = 31.3703))
        sampler.onFix(fix(120_000, lon = 31.3697))
        sampler.onFix(fix(200_000, lon = 31.3702))
        assertEquals(Motion.STATIONARY, sampler.config.motion)
    }

    @Test
    fun `speed or displacement resumes the moving interval immediately`() {
        val sampler = AdaptiveSampler()
        sampler.onFix(fix(0))
        sampler.onFix(fix(200_000))
        assertEquals(Motion.STATIONARY, sampler.config.motion)
        assertEquals(Motion.MOVING, sampler.onFix(fix(201_000, speed = 6f))!!.motion)

        sampler.onFix(fix(500_000, lon = 31.3700))
        assertEquals(Motion.STATIONARY, sampler.config.motion)
        // ~100 m away with no speed reported (some devices omit it).
        assertEquals(Motion.MOVING, sampler.onFix(fix(560_000, lon = 31.3711, speed = null))!!.motion)
    }

    @Test
    fun `imprecise fixes are ignored for motion decisions`() {
        val sampler = AdaptiveSampler()
        sampler.onFix(fix(0))
        sampler.onFix(fix(200_000))
        assertNull(sampler.onFix(fix(201_000, lon = 31.40, speed = 20f, accuracy = 500f)))
        assertEquals(Motion.STATIONARY, sampler.config.motion)
    }

    @Test
    fun `low battery doubles the interval but never stops tracking`() {
        val sampler = AdaptiveSampler()
        val low = sampler.onPowerChanged(PowerState(batteryPercent = 12, charging = false, powerSaveMode = false))
        assertEquals(20_000, low!!.intervalMillis)
        assertTrue(low.lowPower)
        sampler.onFix(fix(0))
        sampler.onFix(fix(180_000))
        // Slowest possible sampling must stay below the server's 300 s gap threshold.
        assertEquals(120_000, sampler.config.intervalMillis)
        assertTrue(sampler.config.intervalMillis < 300_000)

        val charging = sampler.onPowerChanged(PowerState(batteryPercent = 12, charging = true, powerSaveMode = false))
        assertEquals(60_000, charging!!.intervalMillis)
        assertNull(sampler.onPowerChanged(PowerState(batteryPercent = 13, charging = true, powerSaveMode = false)))
    }

    @Test
    fun `power save mode counts as constrained`() {
        assertTrue(PowerState(batteryPercent = 90, charging = false, powerSaveMode = true).constrained)
        assertTrue(!PowerState(batteryPercent = null, charging = false, powerSaveMode = false).constrained)
    }
}
