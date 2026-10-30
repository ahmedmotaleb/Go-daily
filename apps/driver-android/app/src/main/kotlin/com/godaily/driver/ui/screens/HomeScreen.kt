package com.godaily.driver.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.core.api.Shift
import com.godaily.driver.ui.Dialog
import com.godaily.driver.ui.MainViewModel
import com.godaily.driver.ui.UiState
import com.godaily.driver.ui.theme.Brand

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(state: UiState, vm: MainViewModel) {
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(state.message) {
        state.message?.let {
            snackbar.showSnackbar(it)
            vm.consumeMessage()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.driverName ?: "Go Daily", fontWeight = FontWeight.Bold) },
                actions = {
                    TextButton(onClick = vm::refresh, enabled = !state.refreshing) {
                        Text("تحديث", color = Color.White)
                    }
                    TextButton(onClick = vm::logout) { Text("خروج", color = Color.White) }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Brand.Forest800,
                    titleContentColor = Color.White,
                ),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (state.refreshing || state.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (state.stale) {
                Text(
                    "لا يوجد اتصال — البيانات المعروضة قد لا تكون محدثة",
                    color = Brand.Warning,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            TrackingCard(
                status = state.tracking,
                onRestart = vm::restartTracking,
                onPermissions = { vm.showPermissions(true) },
                onRetrySync = vm::retrySync,
            )
            if (state.pendingEnd) PendingEndCard(onRetry = vm::retrySync)

            val active = state.active?.takeIf { it.isActive && !state.pendingEnd }
            if (active != null) {
                ActiveShiftCard(active, state, vm)
            } else {
                StartShiftSection(state, vm)
            }
            VehiclesCard(state)
        }
    }

    when (val dialog = state.dialog) {
        is Dialog.StartShift -> StartShiftDialog(state, dialog.planned, vm)
        Dialog.EndShift -> EndShiftDialog(state, vm)
        Dialog.ChangeOperation -> OperationDialog(state, vm)
        null -> Unit
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            content()
        }
    }
}

@Composable
private fun PendingEndCard(onRetry: () -> Unit) {
    SectionCard("إنهاء الوردية بانتظار الإرسال") {
        Text("توقف التتبع. سيتم إرسال إنهاء الوردية وباقي النقاط تلقائيًا عند عودة الإنترنت.")
        OutlinedButton(onClick = onRetry) { Text("إعادة المحاولة الآن") }
    }
}

@Composable
private fun ActiveShiftCard(shift: Shift, state: UiState, vm: MainViewModel) {
    SectionCard("الوردية الحالية") {
        Text("المركبة: ${shift.vehicle.internalCode} — ${shift.vehicle.plateNumber}")
        Text("بدأت: ${formatTime(shift.startedAt)} · المدة: ${formatDuration(shift.durationMinutes)}")
        shift.startOdometerKm?.let { Text("عداد البداية: $it كم") }
        val session = shift.activeSession
        if (session != null) {
            Text(
                "التشغيل الحالي: ${session.operationType.nameAr}" + (session.route?.let { " — ${it.name}" } ?: ""),
                fontWeight = FontWeight.SemiBold,
            )
            if (session.route != null) {
                Text("الدورات المكتملة: ${session.loops} · الرحلات: ${session.legs}")
            }
        } else {
            Text("لم يُحدد التشغيل الحالي", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = vm::openChangeOperation, enabled = !state.busy) { Text("تغيير التشغيل") }
            if (session != null) {
                OutlinedButton(onClick = vm::endSession, enabled = !state.busy) { Text("إنهاء التشغيل") }
            }
        }
        Button(
            onClick = vm::openEndShift,
            enabled = !state.busy,
            colors = androidx.compose.material3.ButtonDefaults.buttonColors(containerColor = Brand.Danger),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) { Text("إنهاء الوردية", fontSize = 18.sp) }
    }
}

@Composable
private fun StartShiftSection(state: UiState, vm: MainViewModel) {
    val planned = state.today.filter { it.isPlanned }
    if (planned.isNotEmpty()) {
        SectionCard("ورديات اليوم المخططة") {
            planned.forEach { shift ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(shift.vehicle.internalCode, fontWeight = FontWeight.SemiBold)
                        Text(
                            listOfNotNull(
                                shift.plannedStartAt?.let { "الموعد ${formatTime(it)}" },
                                shift.plannedOperationType?.nameAr,
                                shift.plannedRoute?.name,
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Button(onClick = { vm.openStartShift(shift) }, enabled = !state.busy) { Text("بدء") }
                }
            }
        }
    }
    val done = state.today.filter { it.status == "COMPLETED" }
    if (done.isNotEmpty()) {
        SectionCard("ورديات منتهية اليوم") {
            done.forEach { Text("${it.vehicle.internalCode} · ${formatTime(it.startedAt)} – ${formatTime(it.endedAt)}") }
        }
    }
    val hasVehicle = state.me?.vehicles?.isNotEmpty() == true
    Button(
        onClick = { vm.openStartShift(null) },
        enabled = hasVehicle && !state.busy && !state.pendingEnd,
        modifier = Modifier.fillMaxWidth().height(56.dp),
    ) { Text("بدء وردية", fontSize = 18.sp) }
    if (state.me != null && !hasVehicle) {
        Text("لا توجد مركبة مسندة إليك حاليًا. تواصل مع إدارة التشغيل.", color = Brand.Warning)
    }
}

@Composable
private fun VehiclesCard(state: UiState) {
    val vehicles = state.me?.vehicles ?: return
    SectionCard("المركبات المسندة") {
        if (vehicles.isEmpty()) Text("لا توجد مركبات مسندة")
        vehicles.forEach { v ->
            Text(
                "${v.internalCode} — ${v.plateNumber} · ${v.vehicleType} · " +
                    if (v.assignmentRole == "PRIMARY") "أساسي" else "بديل",
            )
        }
    }
}
