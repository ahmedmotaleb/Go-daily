package com.godaily.driver.core.cash

import java.math.BigDecimal
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class CloseoutTest {
    // The design's example: 2,940 − (240 + 150 + 120 + 450) = 1,980.
    private val full = CloseoutDraft(
        endOdometer = "184,414",
        collection = "2940",
        gasQuantity = "24",
        gasAmount = "240",
        gasolineQuantity = "8",
        gasolineAmount = "150",
        toll = "120",
        maintenanceKind = MaintenanceKind.MAINTENANCE,
        maintenanceAmount = "450",
        maintenanceNote = " تغيير تيل فرامل أمامي ",
    )

    @Test
    fun `net is collection less every expense line`() {
        val totals = closeoutTotals(full)
        assertEquals(BigDecimal("960"), totals.expenses)
        assertEquals(BigDecimal("1980"), totals.net)
        assertEquals("1,980", egp(totals.net))
        // Maintenance chosen as "none" does not count even if an amount was typed before.
        assertEquals(BigDecimal("2430"), closeoutTotals(full.copy(maintenanceKind = MaintenanceKind.NONE)).net)
    }

    @Test
    fun `a complete draft becomes the request the API expects`() {
        val check = checkCloseout(full, startOdometerKm = 184_326)
        assertTrue(check is CloseoutCheck.Valid, check.toString())
        val request = (check as CloseoutCheck.Valid).request
        assertEquals(184_414, request.endOdometerKm)
        assertEquals("2940", request.collectionAmount)
        assertEquals("24", request.gasQuantity)
        assertEquals("MAINTENANCE", request.maintenanceKind)
        assertEquals("تغيير تيل فرامل أمامي", request.maintenanceNote)
    }

    @Test
    fun `arabic digits and blanks for optional fuel are accepted`() {
        val draft = CloseoutDraft(endOdometer = "١٨٤٤١٤", collection = "١٤٠٠", toll = "٠")
        val request = (checkCloseout(draft, 184_326) as CloseoutCheck.Valid).request
        assertEquals("1400", request.collectionAmount)
        assertEquals("0", request.gasAmount)
        assertNull(request.gasQuantity)
        assertNull(request.maintenanceNote)
    }

    @Test
    fun `missing pieces are reported per field`() {
        val check = checkCloseout(
            CloseoutDraft(
                endOdometer = "100",
                collection = "",
                gasAmount = "240",
                gasolineQuantity = "5",
                toll = "",
                maintenanceKind = MaintenanceKind.OIL_CHANGE,
                maintenanceAmount = "0",
            ),
            startOdometerKm = 184_326,
        ) as CloseoutCheck.Invalid
        assertEquals(
            setOf(
                "end_odometer_km",
                "collection_amount",
                "gas_quantity",
                "gasoline_amount",
                "toll_amount",
                "maintenance_amount",
                "maintenance_note",
            ),
            check.errors.keys,
        )
        assertEquals("أدخل مبلغ الكارتة (اكتب 0 لو مفيش)", check.errors["toll_amount"])
    }

    @Test
    fun `an already ended shift keeps its end reading`() {
        val request = (
            checkCloseout(full.copy(endOdometer = ""), startOdometerKm = 100, fixedEndOdometerKm = 188) as CloseoutCheck.Valid
            ).request
        assertEquals(188, request.endOdometerKm)
    }

    @Test
    fun `pounds are formatted with separators and a real minus`() {
        assertEquals("2,940", egp("2940.00"))
        assertEquals("1,980.50", egp("1980.5"))
        assertEquals("−150", egp(BigDecimal("-150")))
        assertEquals("0", egp("0.00"))
    }
}
