package com.godaily.driver.core.tracking

import com.godaily.driver.core.api.PointSource
import java.time.Instant
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class LocationFixTest {
    private val base = LocationFix(
        timeMillis = 1_772_346_600_000,
        latitude = 31.0409,
        longitude = 31.3785,
        accuracyM = 7.5f,
        speedMps = 11.2f,
        bearingDeg = 270f,
        altitudeM = 12.0,
        provider = "fused",
    )

    @Test
    fun `maps a fix to the upload model`() {
        val p = base.toGpsPoint("id-1")!!
        assertEquals("id-1", p.clientPointId)
        assertEquals(Instant.ofEpochMilli(base.timeMillis), p.recordedAt)
        assertEquals(31.0409, p.latitude)
        assertEquals(7.5, p.accuracyM)
        assertEquals(PointSource.FUSED, p.source)
        assertFalse(p.isMock)
    }

    @Test
    fun `out-of-range measurements are dropped, coordinates kept as is`() {
        val p = base.copy(speedMps = 250f, bearingDeg = -1f, altitudeM = 20_000.0, accuracyM = Float.NaN)
            .toGpsPoint("id")!!
        assertNull(p.speedMps)
        assertNull(p.headingDeg)
        assertNull(p.altitudeM)
        assertNull(p.accuracyM)
        assertEquals(31.3785, p.longitude)
    }

    @Test
    fun `impossible coordinates are discarded, never corrected`() {
        assertNull(base.copy(latitude = 91.0).toGpsPoint("x"))
        assertNull(base.copy(longitude = Double.NaN).toGpsPoint("x"))
        assertNull(base.copy(latitude = 0.0, longitude = 0.0).toGpsPoint("x"))
    }

    @Test
    fun `mock locations are flagged for the server`() {
        assertTrue(base.copy(isMock = true).toGpsPoint("x")!!.isMock)
        assertEquals(PointSource.GPS, base.copy(provider = "gps").toGpsPoint("x")!!.source)
        assertEquals(PointSource.UNKNOWN, base.copy(provider = null).toGpsPoint("x")!!.source)
    }

    @Test
    fun `repeated or older fixes are skipped`() {
        val dedupe = FixDeduplicator()
        assertTrue(dedupe.accept(base))
        assertFalse(dedupe.accept(base))
        assertFalse(dedupe.accept(base.copy(timeMillis = base.timeMillis - 1)))
        assertTrue(dedupe.accept(base.copy(timeMillis = base.timeMillis + 1)))
    }
}
