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

    @Test
    fun `decimals are validated as text, never as floats`() {
        assertEquals(DecimalInput.Valid("84.50"), parsePositiveDecimal("٨٤٫٥٠", 2, "المبلغ"))
        assertEquals(DecimalInput.Valid("12.5"), parsePositiveDecimal(" 12,5 ", 3, "الكمية"))
        assertEquals(DecimalInput.Valid("0.75"), parsePositiveDecimal("00.75", 2, "المبلغ"))
        assertEquals(DecimalInput.Valid("140"), parsePositiveDecimal("0140", 2, "المبلغ"))
        assertEquals(DecimalInput.Invalid("أدخل المبلغ"), parsePositiveDecimal("", 2, "المبلغ"))
        assertEquals(DecimalInput.Invalid("المبلغ أرقام فقط"), parsePositiveDecimal("1e3", 2, "المبلغ"))
        assertEquals(DecimalInput.Invalid("المبلغ أرقام فقط"), parsePositiveDecimal("-5", 2, "المبلغ"))
        assertEquals(
            DecimalInput.Invalid("المبلغ بحد أقصى 2 أرقام عشرية"),
            parsePositiveDecimal("1.234", 2, "المبلغ"),
        )
        assertEquals(
            DecimalInput.Invalid("المبلغ يجب أن يكون أكبر من صفر"),
            parsePositiveDecimal("0.00", 2, "المبلغ"),
        )
    }
}
