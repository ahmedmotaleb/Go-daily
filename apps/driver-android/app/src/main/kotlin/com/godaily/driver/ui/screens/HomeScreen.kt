package com.godaily.driver.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.R
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.text.ArabicText
import com.godaily.driver.ui.Dialog
import com.godaily.driver.ui.MainViewModel
import com.godaily.driver.ui.UiState
import com.godaily.driver.ui.theme.Brand
import kotlinx.coroutines.delay

/**
 * Driver home (design: تطبيق السائق — الرئيسية): dark header with the
 * greeting and the always-visible tracking state, the vehicle of the day,
 * then the one thing to do now (start the shift, or run and end it).
 */
@Composable
fun HomeScreen(state: UiState, vm: MainViewModel) {
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(state.message) {
        state.message?.let {
            snackbar.showSnackbar(it)
            vm.consumeMessage()
        }
    }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(1_000)
            now = System.currentTimeMillis()
        }
    }
    val active = state.active?.takeIf { it.isActive && !state.pendingEnd }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Brand.Page,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
        ) {
            Header(state, vm, now, shiftEndedToday = active == null && state.today.any { it.status == "COMPLETED" })
            Column(
                verticalArrangement = Arrangement.spacedBy(14.dp),
                modifier = Modifier
                    .offset(y = (-44).dp)
                    .padding(horizontal = 16.dp)
                    .navigationBarsPadding(),
            ) {
                VehicleCard(state, active)
                if (state.refreshing || state.busy) {
                    LinearProgressIndicator(
                        color = Brand.Forest,
                        trackColor = Brand.Line,
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(99.dp)),
                    )
                }
                if (state.stale) {
                    Notice("لا يوجد اتصال — البيانات المعروضة قد لا تكون محدثة", Brand.WarningSoft, Brand.Warning)
                }
                if (state.pendingEnd) PendingEndCard(onRetry = vm::retrySync)
                if (active != null) {
                    ActiveShift(active, state, vm, now)
                } else {
                    StartShiftSection(state, vm)
                }
                OtherVehicles(state)
            }
        }
    }

    when (val dialog = state.dialog) {
        is Dialog.StartShift -> StartShiftDialog(state, dialog.planned, vm)
        Dialog.EndShift -> EndShiftDialog(state, vm)
        Dialog.ChangeOperation -> OperationDialog(state, vm)
        Dialog.RecordFuel -> FuelDialog(state, vm)
        null -> Unit
    }
}

@Composable
private fun Header(state: UiState, vm: MainViewModel, now: Long, shiftEndedToday: Boolean) {
    Column(
        verticalArrangement = Arrangement.spacedBy(16.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(bottomStart = 28.dp, bottomEnd = 28.dp))
            .background(Brand.Forest)
            .statusBarsPadding()
            .padding(start = 20.dp, end = 20.dp, top = 18.dp, bottom = 64.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(
                painterResource(R.drawable.logo_on_dark),
                contentDescription = "GO DAILY",
                contentScale = ContentScale.FillWidth,
                modifier = Modifier.width(92.dp),
            )
            Box(Modifier.weight(1f))
            HeaderAction(R.drawable.ic_refresh, "تحديث", enabled = !state.refreshing, onClick = vm::refresh)
            Box(Modifier.width(8.dp))
            HeaderAction(R.drawable.ic_logout, "تسجيل الخروج", onClick = vm::logout)
        }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                ArabicText.greeting(cairoHour(now), state.me?.fullName ?: state.driverName),
                color = Color.White,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.semantics { heading() },
            )
            Text(formatLongDate(now), color = Brand.OnDarkMuted, fontSize = 13.sp)
        }
        TrackingPill(state.tracking, now, shiftEndedToday, onOpen = { vm.showTracking(true) })
    }
}

@Composable
private fun HeaderAction(icon: Int, label: String, enabled: Boolean = true, onClick: () -> Unit) {
    IconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier
            .size(44.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(Color.White.copy(alpha = 0.08f)),
    ) {
        Icon(painterResource(icon), contentDescription = label, tint = Color.White, modifier = Modifier.size(22.dp))
    }
}

@Composable
private fun Notice(text: String, background: Color, content: Color) {
    Text(
        text,
        color = content,
        fontSize = 13.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(background)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    )
}

/** «سيارتك اليوم»: the shift's vehicle, or the primary assigned one. */
@Composable
private fun VehicleCard(state: UiState, active: Shift?) {
    val vehicles = state.me?.vehicles.orEmpty()
    val vehicle = active?.let { s -> vehicles.firstOrNull { it.id == s.vehicle.id } }
        ?: vehicles.firstOrNull { it.assignmentRole == "PRIMARY" }
        ?: vehicles.firstOrNull()
    val plate = active?.vehicle?.plateNumber ?: vehicle?.plateNumber
    if (plate == null) {
        GdCard(raised = true) {
            Text("لا توجد سيارة مسندة إليك حاليًا", fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text("تواصل مع إدارة التشغيل لإسناد سيارة قبل بدء الوردية.", fontSize = 13.sp, color = Brand.InkSoft)
        }
        return
    }
    val session = active?.activeSession
    GdCard(raised = true) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(if (active != null) "سيارة الوردية" else "سيارتك اليوم", fontSize = 12.sp, color = Brand.InkMuted)
                Text(
                    listOfNotNull(vehicle?.vehicleType, active?.vehicle?.internalCode ?: vehicle?.internalCode)
                        .joinToString(" · "),
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                val plan = session?.let { it.operationType.nameAr + (it.route?.let { r -> " · ${r.name}" } ?: "") }
                    ?: state.today.firstOrNull { it.isPlanned }?.let { p ->
                        listOfNotNull(p.plannedRoute?.name ?: p.plannedOperationType?.nameAr, p.plannedStartAt?.let(::formatTime))
                            .joinToString(" · ")
                    }
                if (!plan.isNullOrBlank()) Text(plan, fontSize = 13.sp, color = Brand.InkSoft)
            }
            PlateBadge(plate)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val odometer = active?.startOdometerKm ?: vehicle?.lastOdometerKm
            StatTile(
                if (active != null) "عداد البداية" else "آخر قراءة عداد",
                odometer?.let { "${formatKm(it)} كم" } ?: "—",
                Modifier.weight(1f),
            )
            StatTile(
                "الإسناد",
                when (vehicle?.assignmentRole) {
                    "PRIMARY" -> "سائق أساسي"
                    null -> "—"
                    else -> "سائق بديل"
                },
                Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun PendingEndCard(onRetry: () -> Unit) {
    GdCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(R.drawable.ic_upload, Brand.WarningSoft, Brand.Warning, size = 44.dp, shape = RoundedCornerShape(14.dp))
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("إنهاء الوردية بانتظار الإرسال", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Text(
                    "توقف التتبع. يُرسل إنهاء الوردية وباقي المواقع تلقائيًا عند عودة الإنترنت.",
                    fontSize = 13.sp,
                    color = Brand.InkSoft,
                )
            }
        }
        SecondaryButton("إعادة المحاولة الآن", onRetry, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
private fun ActiveShift(shift: Shift, state: UiState, vm: MainViewModel, now: Long) {
    val session = shift.activeSession
    Column(
        verticalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Brand.ForestDark)
            .padding(18.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "الوردية جارية منذ ${formatTime(shift.startedAt)}",
                color = Brand.OnDarkMuted,
                fontSize = 13.sp,
                modifier = Modifier.weight(1f),
            )
            Pill("نشطة", Brand.Lime, Brand.ForestDark)
        }
        // Digits read left to right even in the RTL layout.
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Text(
                shift.startedAt?.let { formatElapsed(now - it.toEpochMilli()) } ?: "—",
                color = Color.White,
                fontSize = 40.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                textAlign = TextAlign.End,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("لفات مكتملة", session?.takeIf { it.route != null }?.loops?.toString() ?: "—", Modifier.weight(1f), dark = true, valueSize = 18.sp)
            StatTile("رحلات", session?.takeIf { it.route != null }?.legs?.toString() ?: "—", Modifier.weight(1f), dark = true, valueSize = 18.sp)
            StatTile("عداد البداية", shift.startOdometerKm?.let(::formatKm) ?: "—", Modifier.weight(1f), dark = true)
        }
        Column(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(14.dp))
                .background(Color.White.copy(alpha = 0.07f))
                .padding(12.dp),
        ) {
            Text("التشغيل الحالي", color = Brand.OnDarkMuted, fontSize = 11.sp)
            Text(
                session?.let { it.operationType.nameAr + (it.route?.let { r -> " — ${r.name}" } ?: "") }
                    ?: "لم يُحدد التشغيل الحالي",
                color = Color.White,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SecondaryButton(
                    "تغيير التشغيل",
                    vm::openChangeOperation,
                    modifier = Modifier.weight(1f),
                    enabled = !state.busy,
                    height = 44.dp,
                    icon = R.drawable.ic_swap,
                )
                if (session != null) {
                    SecondaryButton("إنهاء التشغيل", vm::endSession, modifier = Modifier.weight(1f), enabled = !state.busy, height = 44.dp)
                }
            }
        }
    }
    SecondaryButton(
        "تسجيل وقود أو زيت",
        vm::openFuel,
        modifier = Modifier.fillMaxWidth(),
        enabled = !state.busy,
        icon = R.drawable.ic_fuel,
    )
    ForestButton("إنهاء الوردية", vm::openEndShift, enabled = !state.busy, height = 64.dp, icon = R.drawable.ic_stop)
}

@Composable
private fun StartShiftSection(state: UiState, vm: MainViewModel) {
    val planned = state.today.filter { it.isPlanned }
    val hasVehicle = state.me?.vehicles?.isNotEmpty() == true
    if (planned.isNotEmpty()) {
        GdCard {
            Text("ورديات اليوم المخططة", fontSize = 15.sp, fontWeight = FontWeight.Bold)
            planned.forEach { shift ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(shift.vehicle.plateNumber, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            listOfNotNull(
                                shift.plannedStartAt?.let { "الموعد ${formatTime(it)}" },
                                shift.plannedOperationType?.nameAr,
                                shift.plannedRoute?.name,
                            ).joinToString(" · "),
                            fontSize = 13.sp,
                            color = Brand.InkSoft,
                        )
                    }
                    PrimaryButton(
                        "بدء",
                        { vm.openStartShift(shift) },
                        modifier = Modifier.width(96.dp),
                        enabled = !state.busy && !state.pendingEnd,
                        height = 48.dp,
                    )
                }
            }
        }
    }
    PrimaryButton(
        "بدء الوردية",
        { vm.openStartShift(null) },
        enabled = hasVehicle && !state.busy && !state.pendingEnd,
        height = 72.dp,
        icon = R.drawable.ic_play,
    )
    val done = state.today.filter { it.status == "COMPLETED" }
    if (done.isNotEmpty()) {
        GdCard {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                IconTile(R.drawable.ic_check, Brand.SuccessSoft, Brand.Success, size = 44.dp, shape = RoundedCornerShape(14.dp))
                Text("ورديات منتهية اليوم", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }
            done.forEach {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(it.vehicle.plateNumber, fontSize = 14.sp, color = Brand.InkSoft)
                    Text("${formatTime(it.startedAt)} – ${formatTime(it.endedAt)}", fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

/** Only when more than one vehicle is assigned (the main one is on the vehicle card). */
@Composable
private fun OtherVehicles(state: UiState) {
    val vehicles = state.me?.vehicles.orEmpty()
    if (vehicles.size < 2) return
    GdCard {
        Text("السيارات المسندة", fontSize = 15.sp, fontWeight = FontWeight.Bold)
        vehicles.forEach { v ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${v.internalCode} · ${v.vehicleType}", fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                    Text(if (v.assignmentRole == "PRIMARY") "أساسي" else "بديل", fontSize = 12.sp, color = Brand.InkMuted)
                }
                Text(v.plateNumber, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
    Box(Modifier.height(4.dp))
}
