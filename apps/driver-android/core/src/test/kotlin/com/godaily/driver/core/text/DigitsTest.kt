package com.godaily.driver.core.text

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class DigitsTest {
    @Test
    fun `Arabic-Indic digits are normalised`() {
        assertEquals("120450", normalizeDigits("١٢٠٤٥٠"))
        assertEquals("2026", normalizeDigits("۲۰۲۶"))
        assertEquals("abc 12", normalizeDigits("abc ١2"))
    }

    @Test
    fun `odometer readings parse from either keyboard`() {
        assertEquals(OdometerInput.Valid(120_450), parseOdometer(" ١٢٠٤٥٠ "))
        assertEquals(OdometerInput.Valid(120_450), parseOdometer("120,450"))
        assertEquals(OdometerInput.Valid(0), parseOdometer("0"))
    }

    @Test
    fun `bad readings explain why in Arabic`() {
        assertEquals(OdometerInput.Invalid("أدخل قراءة العداد"), parseOdometer("  "))
        assertEquals(OdometerInput.Invalid("قراءة العداد أرقام فقط"), parseOdometer("12.5"))
        assertEquals(OdometerInput.Invalid("قراءة العداد أرقام فقط"), parseOdometer("-4"))
        assertEquals(OdometerInput.Invalid("قراءة العداد غير منطقية"), parseOdometer("99999999999"))
        assertEquals(
            OdometerInput.Invalid("القراءة أقل من آخر قراءة مسجلة (1000 كم)"),
            parseOdometer("999", minimumKm = 1000),
        )
    }
}
