package com.godaily.driver.ui.screens

import android.content.ActivityNotFoundException
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.core.api.DriverCatalog
import com.godaily.driver.core.api.Shift
import com.godaily.driver.receipt.ReceiptPhotos
import com.godaily.driver.ui.MainViewModel
import com.godaily.driver.ui.UiState
import com.godaily.driver.ui.theme.Brand

@Composable
private fun Choice(label: String, selected: Boolean, onClick: () -> Unit) = ChoiceRow(label, selected, onClick)

@Composable
private fun DialogError(error: String?) = FormError(error)

/** Numeric field in the sheets: large bold digits, label above (design: start sheet). */
@Composable
private fun NumberField(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    hint: String? = null,
    decimal: Boolean = false,
) {
    FieldLabel(label)
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        singleLine = true,
        textStyle = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.Bold),
        supportingText = if (hint != null) {
            { Text(hint) }
        } else {
            null
        },
        keyboardOptions = KeyboardOptions(keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number),
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
    )
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
    FieldLabel("نوع التشغيل")
    if (optional) Choice("بدون تحديد الآن", typeId == null) { onType(null); onRoute(null) }
    types.forEach { t -> Choice(t.nameAr, typeId == t.id) { onType(t.id); onRoute(null) } }
    val selected = types.firstOrNull { it.id == typeId }
    val routes = catalog?.routes?.filter { it.operationTypeId == typeId }.orEmpty()
    if (selected?.usesRoutes == true && routes.isNotEmpty()) {
        FieldLabel("الخط")
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
    // Saveable: the activity can be recreated while the camera app is open.
    var photo by rememberSaveable { mutableStateOf<Uri?>(null) }
    val vehicle = vehicles.firstOrNull { it.id == vehicleId }

    GdSheet(
        title = if (planned != null) "بدء الوردية المخططة" else "بدء الوردية",
        onDismiss = vm::closeDialog,
        confirm = {
            PrimaryButton(
                if (photo == null) "صوّر العداد أولًا لبدء الوردية" else "تأكيد بدء الوردية",
                { vehicle?.let { vm.startShift(it, odometer, planned, typeId, routeId, photo) } },
                enabled = vehicle != null && photo != null && !state.busy,
            )
        },
    ) {
        FieldLabel("السيارة")
        vehicles.forEach { v ->
            Choice("${v.plateNumber} · ${v.internalCode}", vehicleId == v.id) {
                if (planned == null) vehicleId = v.id
            }
        }
        NumberField(
            "1 · قراءة العداد الآن (كم)",
            odometer,
            { odometer = it },
            hint = vehicle?.lastOdometerKm?.let { "آخر قراءة: ${formatKm(it)} كم" },
        )
        FieldLabel("2 · صورة العداد (مطلوبة)")
        PhotoCapture(
            photo = photo,
            onPhoto = { photo = it },
            takeLabel = "صوّر العداد",
            hint = "لازم تكون الأرقام واضحة في الصورة",
            takenLabel = "تم التقاط الصورة",
            onCameraMissing = { vm.showDialogError("لا يوجد تطبيق كاميرا على الهاتف") },
        )
        OperationPicker(state.catalog, typeId, routeId, { typeId = it }, { routeId = it }, optional = true)
        Text(
            "يبدأ تتبع موقع السيارة تلقائيًا ويتوقف عند إنهاء الوردية.",
            fontSize = 13.sp,
            color = Brand.InkSoft,
        )
        DialogError(state.dialogError)
    }
}

/** «تسجيل اليوم إجازة؟»: no shift and no tracking today; management sees it. */
@Composable
fun DayOffDialog(state: UiState, vm: MainViewModel) {
    var note by remember { mutableStateOf("") }
    GdSheet(
        title = "تسجيل اليوم إجازة؟",
        onDismiss = vm::closeDialog,
        dismissLabel = "رجوع",
        confirm = {
            ForestButton("تأكيد الإجازة", { vm.registerDayOff(note) }, enabled = !state.busy, height = 56.dp)
        },
    ) {
        Text(
            "${formatLongDate(System.currentTimeMillis())} · لن تبدأ وردية ولن يعمل التتبع اليوم، وسيظهر ذلك للإدارة.",
            fontSize = 13.sp,
            color = Brand.InkSoft,
        )
        FieldLabel("ملاحظة (اختياري)")
        OutlinedTextField(
            value = note,
            onValueChange = { note = it.take(300) },
            placeholder = { Text("مثال: السيارة في الصيانة") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        DialogError(state.dialogError)
    }
}

@Composable
fun OperationDialog(state: UiState, vm: MainViewModel) {
    var typeId by remember { mutableStateOf<String?>(null) }
    var routeId by remember { mutableStateOf<String?>(null) }

    GdSheet(
        title = "تغيير التشغيل الحالي",
        onDismiss = vm::closeDialog,
        confirm = {
            PrimaryButton("تأكيد", { vm.startSession(typeId, routeId) }, enabled = typeId != null && !state.busy)
        },
    ) {
        OperationPicker(state.catalog, typeId, routeId, { typeId = it }, { routeId = it }, optional = false)
        DialogError(state.dialogError)
    }
}

@Composable
fun FuelDialog(state: UiState, vm: MainViewModel) {
    val context = LocalContext.current
    val types = state.catalog?.fuelTypes.orEmpty()
    var typeId by remember { mutableStateOf(types.firstOrNull()?.id) }
    var quantity by remember { mutableStateOf("") }
    var total by remember { mutableStateOf("") }
    var odometer by remember { mutableStateOf("") }
    var paidByDriver by remember { mutableStateOf(true) }
    // Saveable: the activity can be recreated while the camera app is open.
    var receipt by rememberSaveable { mutableStateOf<Uri?>(null) }
    var pendingCapture by rememberSaveable { mutableStateOf<Uri?>(null) }
    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        if (saved) receipt = pendingCapture
    }
    val pickImage = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) receipt = uri
    }

    GdSheet(
        title = "تسجيل وقود أو زيت",
        onDismiss = vm::closeDialog,
        confirm = {
            PrimaryButton(
                "حفظ",
                { vm.recordFuel(typeId, quantity, total, odometer, paidByDriver, receipt) },
                enabled = !state.busy,
            )
        },
    ) {
        FieldLabel("النوع")
        if (types.isEmpty()) FormError("حدّث الشاشة لتحميل الأنواع")
        types.forEach { t -> Choice(t.nameAr, typeId == t.id) { typeId = t.id } }
        NumberField("الكمية", quantity, { quantity = it }, decimal = true)
        NumberField("المبلغ المدفوع (ج.م)", total, { total = it }, decimal = true)
        NumberField("قراءة العداد (اختياري)", odometer, { odometer = it })
        FieldLabel("من دفع؟")
        Choice("دفعت أنا (يُضاف لحسابي بعد المراجعة)", paidByDriver) { paidByDriver = true }
        Choice("دفعت الشركة", !paidByDriver) { paidByDriver = false }

        FieldLabel("صورة الإيصال (اختياري)")
        if (receipt == null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondaryButton(
                    "تصوير",
                    {
                        val target = ReceiptPhotos.newCaptureUri(context)
                        pendingCapture = target
                        try {
                            takePicture.launch(target)
                        } catch (_: ActivityNotFoundException) {
                            vm.showDialogError("لا يوجد تطبيق كاميرا؛ اختر صورة من المعرض")
                        }
                    },
                    modifier = Modifier.weight(1f),
                )
                SecondaryButton(
                    "اختيار صورة",
                    { pickImage.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    modifier = Modifier.weight(1f),
                )
            }
        } else {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(16.dp))
                    .background(Color(0xFFF4FAE6))
                    .padding(horizontal = 12.dp, vertical = 6.dp),
            ) {
                Text(
                    "تم إرفاق صورة الإيصال",
                    color = Brand.Success,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { receipt = null }) { Text("إزالة") }
            }
        }
        Text(
            "يُرفق موقع السيارة الحالي من تتبع الوردية إن كان حديثًا (آخر دقيقتين).",
            fontSize = 13.sp,
            color = Brand.InkSoft,
        )
        DialogError(state.dialogError)
    }
}
