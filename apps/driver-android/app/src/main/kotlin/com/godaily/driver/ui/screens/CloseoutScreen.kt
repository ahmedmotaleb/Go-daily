package com.godaily.driver.ui.screens

import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.R
import com.godaily.driver.core.cash.CloseoutDraft
import com.godaily.driver.core.cash.MaintenanceKind
import com.godaily.driver.core.cash.closeoutTotals
import com.godaily.driver.core.cash.egp
import com.godaily.driver.ui.MainViewModel
import com.godaily.driver.ui.UiState
import com.godaily.driver.ui.theme.Brand

/**
 * «تقفيل الوردية»: everything about the day's money in one place, entered
 * once at the end of the shift. Submitting ends the shift (if still running)
 * and sends the close-out; the net to hand over updates while typing.
 */
@Composable
fun CloseoutScreen(state: UiState, vm: MainViewModel) {
    val shift = state.closeoutShift ?: return
    BackHandler(onBack = vm::closeCloseout)
    val draft = state.closeoutDraft
    val errors = state.closeoutErrors
    val ended = !shift.isActive
    val totals = closeoutTotals(draft)
    var receipt by rememberSaveable { mutableStateOf<Uri?>(null) }
    fun edit(change: CloseoutDraft) = vm.editCloseout(change)

    Column(Modifier.fillMaxSize().background(Brand.Page)) {
        Box(Modifier.fillMaxWidth().background(Brand.Forest).statusBarsPadding())
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(68.dp)
                .background(Brand.Surface)
                .padding(horizontal = 12.dp),
        ) {
            IconButton(onClick = vm::closeCloseout, modifier = Modifier.size(48.dp)) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = "رجوع للوردية", tint = Brand.Ink)
            }
            Column {
                Text(
                    "تقفيل الوردية",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.semantics { heading() },
                )
                Text(
                    if (ended) "الوردية منتهية — أرسل معاملات اليوم" else "معاملات اليوم كلها هنا",
                    fontSize = 12.sp,
                    color = Brand.InkMuted,
                )
            }
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(Brand.Line))

        Column(
            verticalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(16.dp),
        ) {
            Section("العداد والتحصيل") {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Field(
                        label = "عداد الإنهاء (كم)",
                        value = if (ended) shift.endOdometerKm?.let(::formatKm).orEmpty() else draft.endOdometer,
                        onChange = { edit(draft.copy(endOdometer = it)) },
                        error = errors["end_odometer_km"],
                        enabled = !ended,
                        decimal = false,
                        modifier = Modifier.weight(1f),
                    )
                    Field(
                        label = "إجمالي التحصيل (ج.م)",
                        value = draft.collection,
                        onChange = { edit(draft.copy(collection = it)) },
                        error = errors["collection_amount"],
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            Section("الوقود") {
                FuelRow(
                    label = "غاز",
                    unit = "م³",
                    quantity = draft.gasQuantity,
                    amount = draft.gasAmount,
                    onQuantity = { edit(draft.copy(gasQuantity = it)) },
                    onAmount = { edit(draft.copy(gasAmount = it)) },
                    quantityError = errors["gas_quantity"],
                    amountError = errors["gas_amount"],
                )
                FuelRow(
                    label = "بنزين",
                    unit = "لتر",
                    quantity = draft.gasolineQuantity,
                    amount = draft.gasolineAmount,
                    onQuantity = { edit(draft.copy(gasolineQuantity = it)) },
                    onAmount = { edit(draft.copy(gasolineAmount = it)) },
                    quantityError = errors["gasoline_quantity"],
                    amountError = errors["gasoline_amount"],
                )
                PhotoCapture(
                    photo = receipt,
                    onPhoto = { receipt = it },
                    takeLabel = "صورة إيصال الوقود",
                    hint = "",
                    takenLabel = "تم إرفاق صورة الإيصال",
                    onCameraMissing = {},
                    compact = true,
                )
            }

            Section("الكارتة", badge = "(مطلوبة كل وردية)") {
                Field(
                    label = "مبلغ الكارتة (ج.م) — 0 لو مفيش",
                    value = draft.toll,
                    onChange = { edit(draft.copy(toll = it)) },
                    error = errors["toll_amount"],
                )
            }

            Section("الصيانة والزيت") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(
                        MaintenanceKind.NONE to "لا يوجد",
                        MaintenanceKind.OIL_CHANGE to "تغيير زيت",
                        MaintenanceKind.MAINTENANCE to "صيانة",
                    ).forEach { (kind, label) ->
                        Segment(
                            label = label,
                            selected = draft.maintenanceKind == kind,
                            onClick = { edit(draft.copy(maintenanceKind = kind)) },
                            modifier = Modifier.weight(1f),
                        )
                    }
                }
                if (draft.maintenanceKind != MaintenanceKind.NONE) {
                    Field(
                        label = "التكلفة (ج.م)",
                        value = draft.maintenanceAmount,
                        onChange = { edit(draft.copy(maintenanceAmount = it)) },
                        error = errors["maintenance_amount"],
                    )
                    FieldLabel("ملاحظة — إيه اللي اتعمل؟ (مطلوبة)")
                    OutlinedTextField(
                        value = draft.maintenanceNote,
                        onValueChange = { edit(draft.copy(maintenanceNote = it.take(1000))) },
                        placeholder = { Text("مثال: تغيير زيت موتور وفلتر زيت") },
                        minLines = 2,
                        isError = errors["maintenance_note"] != null,
                        supportingText = noteError(errors["maintenance_note"]),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }

            Summary(totals.collection.toPlainString(), totals.expenses.toPlainString(), totals.net.toPlainString())

            FormError(errors["form"])
            if (state.closeoutOffline && !ended) {
                GdCard {
                    Text(
                        "يمكنك إنهاء الوردية الآن (يتوقف التتبع وتُحفظ البيانات على الهاتف) وإرسال التقفيل من الشاشة الرئيسية عند عودة الإنترنت.",
                        fontSize = 13.sp,
                        color = Brand.InkSoft,
                    )
                    SecondaryButton(
                        "إنهاء الوردية فقط",
                        vm::endShiftWithoutCloseout,
                        modifier = Modifier.fillMaxWidth(),
                        critical = true,
                    )
                }
            }
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brand.Surface)
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .navigationBarsPadding(),
        ) {
            PrimaryButton(
                "إرسال تقفيل اليوم",
                { vm.submitCloseout(receipt) },
                enabled = !state.busy,
                icon = R.drawable.ic_send,
            )
        }
    }
}

private fun noteError(message: String?): (@Composable () -> Unit)? =
    if (message != null) {
        { Text(message) }
    } else {
        null
    }

@Composable
private fun Section(title: String, badge: String? = null, content: @Composable ColumnScope.() -> Unit) {
    GdCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, fontSize = 15.sp, fontWeight = FontWeight.Bold)
            if (badge != null) Text(badge, fontSize = 12.sp, color = Brand.Danger)
        }
        content()
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    error: String?,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    decimal: Boolean = true,
    suffix: String? = null,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (label.isNotEmpty()) Text(label, fontSize = 13.sp, color = Brand.InkSoft)
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            singleLine = true,
            enabled = enabled,
            isError = error != null,
            textStyle = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Bold),
            suffix = if (suffix != null) {
                { Text(suffix, fontSize = 13.sp, color = Brand.InkMuted) }
            } else {
                null
            },
            supportingText = if (error != null) {
                { Text(error) }
            } else {
                null
            },
            keyboardOptions = KeyboardOptions(keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number),
            modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
        )
    }
}

@Composable
private fun FuelRow(
    label: String,
    unit: String,
    quantity: String,
    amount: String,
    onQuantity: (String) -> Unit,
    onAmount: (String) -> Unit,
    quantityError: String?,
    amountError: String?,
) {
    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            label,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.width(48.dp).padding(top = 18.dp),
        )
        Field(
            label = "",
            value = quantity,
            onChange = onQuantity,
            error = quantityError,
            suffix = unit,
            modifier = Modifier.weight(1f),
        )
        Field(
            label = "",
            value = amount,
            onChange = onAmount,
            error = amountError,
            suffix = "ج.م",
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun Segment(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Box(
        contentAlignment = Alignment.Center,
        modifier = modifier
            .height(44.dp)
            .clip(shape)
            .border(if (selected) 2.dp else 1.dp, if (selected) Brand.Forest else Brand.LineStrong, shape)
            .background(if (selected) Brand.ForestSoft else Brand.Surface)
            .selectable(selected = selected, onClick = onClick, role = Role.RadioButton),
    ) {
        Text(
            label,
            fontSize = 14.sp,
            fontWeight = FontWeight.SemiBold,
            color = if (selected) Brand.Forest else Brand.InkSoft,
        )
    }
}

@Composable
private fun Summary(collection: String, expenses: String, net: String) {
    Column(
        verticalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Brand.ForestDark)
            .padding(18.dp),
    ) {
        SummaryLine("إجمالي التحصيل", "${egp(collection)} ج.م")
        SummaryLine("المصروفات (غاز، بنزين، كارتة، صيانة)", "− ${egp(expenses)} ج.م")
        Box(Modifier.fillMaxWidth().height(1.dp).background(Brand.OnDarkMuted.copy(alpha = 0.3f)))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "صافي للتسليم للإدارة",
                color = Brand.LimeText,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Text("${egp(net)} ج.م", color = Brand.Lime, fontSize = 24.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun SummaryLine(label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Brand.OnDarkMuted, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(value, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
    }
}
