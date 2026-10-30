package com.godaily.driver.core.text

/**
 * Converts Arabic-Indic (٠-٩) and Extended Arabic-Indic (۰-۹) digits to
 * ASCII so numbers typed on an Arabic keyboard parse correctly.
 */
fun normalizeDigits(input: String): String = buildString(input.length) {
    for (ch in input) {
        append(
            when (ch) {
                in '٠'..'٩' -> '0' + (ch - '٠')
                in '۰'..'۹' -> '0' + (ch - '۰')
                else -> ch
            },
        )
    }
}

sealed interface OdometerInput {
    data class Valid(val km: Int) : OdometerInput

    data class Invalid(val message: String) : OdometerInput
}

/** Upper bound accepted by the server (Odometer: le=5_000_000). */
const val MAX_ODOMETER_KM = 5_000_000

/**
 * Parses an odometer reading in whole kilometres.
 *
 * [minimumKm] is the reading the vehicle must not go below (the last known
 * odometer, or the shift's start reading when ending a shift).
 */
fun parseOdometer(raw: String, minimumKm: Int? = null): OdometerInput {
    val text = normalizeDigits(raw).trim().replace(",", "").replace("٬", "")
    if (text.isEmpty()) return OdometerInput.Invalid("أدخل قراءة العداد")
    if (!text.all { it in '0'..'9' }) return OdometerInput.Invalid("قراءة العداد أرقام فقط")
    val km = text.toLongOrNull()
    if (km == null || km > MAX_ODOMETER_KM) return OdometerInput.Invalid("قراءة العداد غير منطقية")
    if (minimumKm != null && km < minimumKm) {
        return OdometerInput.Invalid("القراءة أقل من آخر قراءة مسجلة ($minimumKm كم)")
    }
    return OdometerInput.Valid(km.toInt())
}
