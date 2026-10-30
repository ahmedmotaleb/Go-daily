package com.godaily.driver.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.godaily.driver.core.api.DriverCatalog
import com.godaily.driver.core.api.Shift
import com.godaily.driver.ui.MainViewModel
import com.godaily.driver.ui.UiState

@Composable
private fun Choice(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .selectable(selected = selected, onClick = onClick, role = Role.RadioButton),
    ) {
        RadioButton(selected = selected, onClick = null)
        Text(label)
    }
}

@Composable
private fun DialogError(error: String?) {
    if (error != null) Text(error, color = MaterialTheme.colorScheme.error)
}

/** Operation type + optional route pickers, shared by start-shift and change-operation. */
@Composable
private fun OperationPicker(
    catalog: DriverCatalog?,
    typeId: String?,
    routeId: String?,
    onType: (String?) -> Unit,
    onRoute: (String?) -> Unit,
    optional: Boolean,
) {
    val types = catalog?.operationTypes?.filter { it.isActive }.orEmpty()
    Text("نوع التشغيل", fontWeight = FontWeight.SemiBold)
    if (optional) Choice("بدون تحديد الآن", typeId == null) { onType(null); onRoute(null) }
    types.forEach { t -> Choice(t.nameAr, typeId == t.id) { onType(t.id); onRoute(null) } }
    val selected = types.firstOrNull { it.id == typeId }
    val routes = catalog?.routes?.filter { it.operationTypeId == typeId }.orEmpty()
    if (selected?.usesRoutes == true && routes.isNotEmpty()) {
        Text("الخط", fontWeight = FontWeight.SemiBold)
        Choice("بدون خط", routeId == null) { onRoute(null) }
        routes.forEach { r -> Choice(r.name, routeId == r.id) { onRoute(r.id) } }
    }
}

@Composable
fun StartShiftDialog(state: UiState, planned: Shift?, vm: MainViewModel) {
    val vehicles = state.me?.vehicles.orEmpty()
    var vehicleId by remember {
        mutableStateOf(planned?.vehicle?.id ?: vehicles.singleOrNull()?.id)
    }
    var odometer by remember { mutableStateOf("") }
    var typeId by remember { mutableStateOf(planned?.plannedOperationType?.id) }
    var routeId by remember { mutableStateOf(planned?.plannedRoute?.id) }
    val vehicle = vehicles.firstOrNull { it.id == vehicleId }

    AlertDialog(
        onDismissRequest = vm::closeDialog,
        title = { Text(if (planned != null) "بدء الوردية المخططة" else "بدء وردية") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                Text("المركبة", fontWeight = FontWeight.SemiBold)
                vehicles.forEach { v ->
                    Choice("${v.internalCode} — ${v.plateNumber}", vehicleId == v.id) {
                        if (planned == null) vehicleId = v.id
                    }
                }
                OutlinedTextField(
                    value = odometer,
                    onValueChange = { odometer = it },
                    label = { Text("قراءة العداد (كم)") },
                    supportingText = {
                        vehicle?.lastOdometerKm?.let { Text("آخر قراءة: $it كم") }
                    },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                OperationPicker(state.catalog, typeId, routeId, { typeId = it }, { routeId = it }, optional = true)
                Text(
                    "سيبدأ تتبع موقع المركبة تلقائيًا ويتوقف عند إنهاء الوردية.",
                    style = MaterialTheme.typography.bodySmall,
                )
                DialogError(state.dialogError)
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    vehicle?.let { vm.startShift(it, odometer, planned, typeId, routeId) }
                },
                enabled = vehicle != null && !state.busy,
            ) { Text("بدء") }
        },
        dismissButton = { TextButton(onClick = vm::closeDialog) { Text("إلغاء") } },
    )
}

@Composable
fun EndShiftDialog(state: UiState, vm: MainViewModel) {
    val shift = state.active ?: return
    var odometer by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    val pending = state.tracking?.pendingPoints ?: 0

    AlertDialog(
        onDismissRequest = vm::closeDialog,
        title = { Text("إنهاء الوردية") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = odometer,
                    onValueChange = { odometer = it },
                    label = { Text("قراءة العداد عند الانتهاء (كم)") },
                    supportingText = {
                        shift.startOdometerKm?.let { Text("عداد البداية: $it كم") }
                    },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it.take(1000) },
                    label = { Text("ملاحظات (اختياري)") },
                    modifier = Modifier.fillMaxWidth(),
                )
                if (pending > 0) {
                    Text(
                        "يوجد $pending نقطة لم تُرسل بعد. سيتوقف التتبع الآن وتُرسل النقاط تلقائيًا عند توفر الإنترنت.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                DialogError(state.dialogError)
            }
        },
        confirmButton = {
            Button(onClick = { vm.endShift(odometer, notes) }, enabled = !state.busy) { Text("تأكيد الإنهاء") }
        },
        dismissButton = { TextButton(onClick = vm::closeDialog) { Text("رجوع") } },
    )
}

@Composable
fun OperationDialog(state: UiState, vm: MainViewModel) {
    var typeId by remember { mutableStateOf<String?>(null) }
    var routeId by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = vm::closeDialog,
        title = { Text("تغيير التشغيل الحالي") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                OperationPicker(state.catalog, typeId, routeId, { typeId = it }, { routeId = it }, optional = false)
                DialogError(state.dialogError)
            }
        },
        confirmButton = {
            Button(onClick = { vm.startSession(typeId, routeId) }, enabled = typeId != null && !state.busy) {
                Text("تأكيد")
            }
        },
        dismissButton = { TextButton(onClick = vm::closeDialog) { Text("إلغاء") } },
    )
}

@Composable
fun FuelDialog(state: UiState, vm: MainViewModel) {
    val types = state.catalog?.fuelTypes.orEmpty()
    var typeId by remember { mutableStateOf(types.firstOrNull()?.id) }
    var quantity by remember { mutableStateOf("") }
    var total by remember { mutableStateOf("") }
    var odometer by remember { mutableStateOf("") }
    var paidByDriver by remember { mutableStateOf(true) }

    AlertDialog(
        onDismissRequest = vm::closeDialog,
        title = { Text("تسجيل وقود أو زيت") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                Text("النوع", fontWeight = FontWeight.SemiBold)
                if (types.isEmpty()) Text("حدّث الشاشة لتحميل الأنواع", color = MaterialTheme.colorScheme.error)
                types.forEach { t -> Choice(t.nameAr, typeId == t.id) { typeId = t.id } }
                OutlinedTextField(
                    value = quantity,
                    onValueChange = { quantity = it },
                    label = { Text("الكمية") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = total,
                    onValueChange = { total = it },
                    label = { Text("المبلغ المدفوع (جنيه)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = odometer,
                    onValueChange = { odometer = it },
                    label = { Text("قراءة العداد (اختياري)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("من دفع؟", fontWeight = FontWeight.SemiBold)
                Choice("دفعت أنا (يُضاف لحسابي بعد المراجعة)", paidByDriver) { paidByDriver = true }
                Choice("دفعت الشركة", !paidByDriver) { paidByDriver = false }
                DialogError(state.dialogError)
            }
        },
        confirmButton = {
            Button(
                onClick = { vm.recordFuel(typeId, quantity, total, odometer, paidByDriver) },
                enabled = !state.busy,
            ) { Text("حفظ") }
        },
        dismissButton = { TextButton(onClick = vm::closeDialog) { Text("إلغاء") } },
    )
}
