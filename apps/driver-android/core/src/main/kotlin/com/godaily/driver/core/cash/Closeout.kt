package com.godaily.driver.core.cash

import com.godaily.driver.core.api.CloseoutRequest
import com.godaily.driver.core.text.OdometerInput
import com.godaily.driver.core.text.normalizeDigits
import com.godaily.driver.core.text.parseOdometer
import java.math.BigDecimal
import java.util.Locale

enum class MaintenanceKind { NONE, OIL_CHANGE, MAINTENANCE }

/** What the driver typed on «تقفيل الوردية» (raw text, as on screen). */
data class CloseoutDraft(
    val endOdometer: String = "",
    val collection: String = "",
    val gasQuantity: String = "",
    val gasAmount: String = "",
    val gasolineQuantity: String = "",
    val gasolineAmount: String = "",
    val toll: String = "",
    val maintenanceKind: MaintenanceKind = MaintenanceKind.NONE,
    val maintenanceAmount: String = "",
    val maintenanceNote: String = "",
)

sealed interface CloseoutCheck {
    data class Valid(val request: CloseoutRequest) : CloseoutCheck

    /** Field (API name) → Arabic message. */
    data class Invalid(val errors: Map<String, String>) : CloseoutCheck
}

data class CloseoutTotals(val collection: BigDecimal, val expenses: BigDecimal) {
    /** What the driver hands over (negative: the company owes the driver). */
    val net: BigDecimal get() = collection - expenses
}

private val MONEY = Regex("""^\d{1,9}(\.\d{1,2})?$""")
private val QUANTITY = Regex("""^\d{1,9}(\.\d{1,3})?$""")

private fun clean(raw: String): String =
    normalizeDigits(raw).trim().replace('٫', '.').replace("٬", "").replace(",", "")

/** Null when blank; throws nothing: invalid text is reported by [checkCloseout]. */
private fun number(raw: String, pattern: Regex): BigDecimal? {
    val text = clean(raw)
    return if (text.isNotEmpty() && pattern.matches(text)) BigDecimal(text) else null
}

/** Live summary while typing: blank or unfinished fields count as zero. */
fun closeoutTotals(draft: CloseoutDraft): CloseoutTotals {
    fun amount(raw: String) = number(raw, MONEY) ?: BigDecimal.ZERO
    val maintenance =
        if (draft.maintenanceKind == MaintenanceKind.NONE) BigDecimal.ZERO else amount(draft.maintenanceAmount)
    return CloseoutTotals(
        collection = amount(draft.collection),
        expenses = amount(draft.gasAmount) + amount(draft.gasolineAmount) + amount(draft.toll) + maintenance,
    )
}

/**
 * Checks the draft and builds the request. [startOdometerKm] is the shift's
 * start reading; [fixedEndOdometerKm] is set when the shift already ended
 * (the close-out must use that reading).
 */
fun checkCloseout(
    draft: CloseoutDraft,
    startOdometerKm: Int?,
    fixedEndOdometerKm: Int? = null,
): CloseoutCheck {
    val errors = linkedMapOf<String, String>()

    val endKm = fixedEndOdometerKm ?: when (val r = parseOdometer(draft.endOdometer, startOdometerKm)) {
        is OdometerInput.Valid -> r.km
        is OdometerInput.Invalid -> {
            errors["end_odometer_km"] = r.message
            null
        }
    }

    fun money(raw: String, field: String, label: String, required: Boolean): BigDecimal? {
        val text = clean(raw)
        if (text.isEmpty()) {
            if (required) errors[field] = "أدخل $label (اكتب 0 لو مفيش)"
            return if (required) null else BigDecimal.ZERO
        }
        if (!MONEY.matches(text)) {
            errors[field] = "$label أرقام فقط (بحد أقصى رقمين عشريين)"
            return null
        }
        return BigDecimal(text)
    }

    fun quantity(raw: String, field: String, label: String): BigDecimal? {
        val text = clean(raw)
        if (text.isEmpty()) return null
        if (!QUANTITY.matches(text)) {
            errors[field] = "$label أرقام فقط"
            return null
        }
        return BigDecimal(text)
    }

    val collection = money(draft.collection, "collection_amount", "إجمالي التحصيل", required = true)
    val gas = money(draft.gasAmount, "gas_amount", "مبلغ الغاز", required = false)
    val gasQty = quantity(draft.gasQuantity, "gas_quantity", "كمية الغاز")
    val gasoline = money(draft.gasolineAmount, "gasoline_amount", "مبلغ البنزين", required = false)
    val gasolineQty = quantity(draft.gasolineQuantity, "gasoline_quantity", "كمية البنزين")
    val toll = money(draft.toll, "toll_amount", "مبلغ الكارتة", required = true)

    for ((amount, qty, prefix, label) in listOf(
        FuelLine(gas, gasQty, "gas", "الغاز"),
        FuelLine(gasoline, gasolineQty, "gasoline", "البنزين"),
    )) {
        val positive = amount != null && amount.signum() > 0
        val hasQty = qty != null && qty.signum() > 0
        if (positive && !hasQty && "${prefix}_quantity" !in errors) {
            errors["${prefix}_quantity"] = "أدخل كمية $label"
        }
        if (!positive && hasQty && "${prefix}_amount" !in errors) {
            errors["${prefix}_amount"] = "أدخل مبلغ $label"
        }
    }

    var maintenance: BigDecimal? = BigDecimal.ZERO
    val note = draft.maintenanceNote.trim()
    if (draft.maintenanceKind != MaintenanceKind.NONE) {
        maintenance = money(draft.maintenanceAmount, "maintenance_amount", "تكلفة الصيانة", required = true)
        if (maintenance != null && maintenance.signum() == 0) {
            errors["maintenance_amount"] = "أدخل تكلفة الصيانة"
        }
        if (note.isEmpty()) errors["maintenance_note"] = "اكتب إيه اللي اتعمل في الصيانة"
    }

    if (errors.isNotEmpty() || endKm == null || collection == null || toll == null ||
        gas == null || gasoline == null || maintenance == null
    ) {
        return CloseoutCheck.Invalid(errors.ifEmpty { mapOf("form" to "راجع البيانات") })
    }
    return CloseoutCheck.Valid(
        CloseoutRequest(
            endOdometerKm = endKm,
            collectionAmount = collection.toPlainString(),
            gasQuantity = if (gas.signum() > 0) gasQty?.toPlainString() else null,
            gasAmount = gas.toPlainString(),
            gasolineQuantity = if (gasoline.signum() > 0) gasolineQty?.toPlainString() else null,
            gasolineAmount = gasoline.toPlainString(),
            tollAmount = toll.toPlainString(),
            maintenanceKind = draft.maintenanceKind.name,
            maintenanceAmount = maintenance.toPlainString(),
            maintenanceNote = note.ifEmpty { null }?.takeIf { draft.maintenanceKind != MaintenanceKind.NONE },
        ),
    )
}

private data class FuelLine(val amount: BigDecimal?, val qty: BigDecimal?, val prefix: String, val label: String)

/** «2,940» / «1,980.5» / «−150»: pounds with separators, no trailing zeros. */
fun egp(value: BigDecimal): String {
    val stripped = value.stripTrailingZeros()
    val sign = if (stripped.signum() < 0) "−" else ""
    val abs = stripped.abs()
    return sign + if (abs.scale() <= 0) {
        String.format(Locale.ROOT, "%,d", abs.toBigInteger())
    } else {
        String.format(Locale.ROOT, "%,.2f", abs)
    }
}

fun egp(value: String): String = egp(value.toBigDecimalOrNull() ?: BigDecimal.ZERO)

/** Driver-facing words for a close-out's collection state. */
fun collectionStatusLabel(status: String): String = when (status) {
    "WAITING" -> "في انتظار تسجيل التحصيل من الإدارة"
    "PARTIAL" -> "تحصيل جزئي"
    "COLLECTED" -> "تم التحصيل"
    else -> "لا يوجد مبلغ للتسليم"
}
