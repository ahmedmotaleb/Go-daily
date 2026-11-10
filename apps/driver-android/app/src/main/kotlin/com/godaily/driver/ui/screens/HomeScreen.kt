package com.godaily.driver.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.BuildConfig
import com.godaily.driver.R
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.cash.collectionStatusLabel
import com.godaily.driver.core.cash.egp
import com.godaily.driver.core.sync.EntryKind
import com.godaily.driver.core.sync.EntryState
import com.godaily.driver.core.sync.QueuedEntry
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
                // U44: version policy from the server. A running shift is never interrupted.
                val update = state.me?.appUpdate
                if (update?.required == true) {
                    Notice(
                        "يجب تحديث التطبيق قبل بدء وردية جديدة. الوردية الجارية تستمر بشكل عادي.",
                        Brand.DangerSoft,
                        Brand.Danger,
                    )
                } else if (update?.recommended == true) {
                    Notice("يتوفر إصدار أحدث من التطبيق؛ حدّثه في أقرب وقت.", Brand.WarningSoft, Brand.Warning)
                }
                if (state.pendingEnd) PendingEndCard(onRetry = vm::retrySync)
                val kept = state.entries.filter { it.state != EntryState.SYNCED || !it.receiptDone }
                if (kept.isNotEmpty()) SavedEntriesCard(kept, state.busy, vm)
                if (active != null) {
                    ActiveShift(active, state, vm, now)
                } else {
                    StartShiftSection(state, vm)
                    if (state.account?.todayDayOff == null) AccountCard(state, vm)
                }
                OtherVehicles(state)
                Text(
                    "إصدار التطبيق ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})" +
                        if (BuildConfig.ENVIRONMENT != "production") " · نسخة تجريبية" else "",
                    fontSize = 12.sp,
                    color = Brand.InkMuted,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }

    when (val dialog = state.dialog) {
        is Dialog.StartShift -> StartShiftDialog(state, dialog.planned, vm)
        Dialog.DayOff -> DayOffDialog(state, vm)
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

/**
 * «محفوظ على الهاتف» (U45): fuel entries and close-outs saved on the phone
 * and their state. Waiting ones are sent automatically; a refused one shows
 * the office's reason and can be hidden.
 */
@Composable
private fun SavedEntriesCard(entries: List<QueuedEntry>, busy: Boolean, vm: MainViewModel) {
    GdCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(R.drawable.ic_upload, Brand.WarningSoft, Brand.Warning, size = 44.dp, shape = RoundedCornerShape(14.dp))
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("محفوظ على الهاتف", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                Text(
                    "يُرسل تلقائيًا عند عودة الإنترنت، مرة واحدة فقط.",
                    fontSize = 13.sp,
                    color = Brand.InkSoft,
                )
            }
        }
        entries.forEach { entry ->
            val (label, tone) = when {
                entry.state == EntryState.FAILED -> "لم يُقبل" to Brand.Danger
                entry.state == EntryState.SYNCED -> "أُرسل — صورة الإيصال بانتظار الرفع" to Brand.Success
                else -> "بانتظار الإرسال" to Brand.Warning
            }
            Column(
                verticalArrangement = Arrangement.spacedBy(4.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(Brand.Page)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(entry.title, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    Text(formatTime(entry.createdAt), fontSize = 12.sp, color = Brand.InkMuted)
                }
                Text(label, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = tone)
                if (entry.state == EntryState.FAILED) {
                    entry.lastError?.let { Text(it, fontSize = 13.sp, color = Brand.InkSoft) }
                    SecondaryButton("إخفاء", { vm.dismissEntry(entry.clientId) }, modifier = Modifier.fillMaxWidth())
                }
            }
        }
        if (entries.any { it.state != EntryState.FAILED }) {
            SecondaryButton("إعادة المحاولة الآن", vm::retrySync, modifier = Modifier.fillMaxWidth(), enabled = !busy)
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
    Row(
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(Brand.Surface)
            .padding(14.dp),
    ) {
        Icon(
            painterResource(R.drawable.ic_info),
            contentDescription = null,
            tint = Brand.Forest,
            modifier = Modifier.size(20.dp),
        )
        Text(
            "التحصيل والوقود والكارتة والصيانة تُسجَّل كلها مرة واحدة عند تقفيل الوردية في آخر اليوم.",
            fontSize = 13.sp,
            color = Brand.InkSoft,
        )
    }
    ForestButton(
        "إنهاء وتقفيل الوردية",
        { vm.openCloseout(shift) },
        enabled = !state.busy,
        height = 64.dp,
        icon = R.drawable.ic_stop,
    )
}

@Composable
private fun StartShiftSection(state: UiState, vm: MainViewModel) {
    val planned = state.today.filter { it.isPlanned }
    val hasVehicle = state.me?.vehicles?.isNotEmpty() == true
    val account = state.account
    val dayOff = account?.todayDayOff
    if (dayOff != null) {
        DayOffCard(dayOff.note, formatTime(dayOff.createdAt), enabled = !state.busy, onCancel = vm::cancelDayOff)
        AccountCard(state, vm)
        return
    }
    TodayCloseouts(state, vm)
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
    // A day-off is only possible before any shift today.
    if (state.today.none { it.status == "ACTIVE" || it.status == "COMPLETED" } && !state.pendingEnd) {
        SecondaryButton(
            "تسجيل اليوم إجازة",
            vm::openDayOff,
            modifier = Modifier.fillMaxWidth(),
            enabled = !state.busy,
            icon = R.drawable.ic_calendar,
        )
    }
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

@Composable
private fun DayOffCard(note: String?, at: String, enabled: Boolean, onCancel: () -> Unit) {
    GdCard(padding = 20.dp) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            IconTile(R.drawable.ic_calendar, Brand.ForestSoft, Brand.Forest, size = 56.dp, shape = RoundedCornerShape(18.dp))
            Text("اليوم إجازة", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Text(
                "سُجّلت الساعة $at وظهرت للإدارة. لا يوجد تتبع ولا معاملات اليوم." +
                    (note?.let { "\nملاحظة: $it" } ?: ""),
                fontSize = 13.sp,
                color = Brand.InkSoft,
                textAlign = TextAlign.Center,
            )
            SecondaryButton("إلغاء الإجازة", onCancel, enabled = enabled, height = 48.dp)
        }
    }
}

/** Today's close-outs: sent (with the collection state) or still to send for an ended shift. */
@Composable
private fun TodayCloseouts(state: UiState, vm: MainViewModel) {
    val account = state.account ?: return
    val sent = account.todayCloseout
    if (sent != null) {
        GdCard(padding = 18.dp) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                IconTile(R.drawable.ic_check, Brand.SuccessSoft, Brand.Success, size = 44.dp, shape = RoundedCornerShape(14.dp))
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("تم إرسال تقفيل اليوم", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "أُرسل ${formatTime(sent.submittedAt)} · التتبع متوقف",
                        fontSize = 12.sp,
                        color = Brand.InkMuted,
                    )
                }
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(Brand.Page)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
            ) {
                Text("صافي للتسليم", fontSize = 14.sp, color = Brand.InkSoft, modifier = Modifier.weight(1f))
                Text("${egp(sent.netAmount)} ج.م", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
            val (soft, tone, dot) = when (sent.status) {
                "COLLECTED" -> Triple(Brand.SuccessSoft, Brand.Success, Brand.SuccessDot)
                "PARTIAL" -> Triple(Brand.DangerSoft, Brand.Danger, Brand.DangerDot)
                "WAITING" -> Triple(Brand.WarningSoft, Brand.Warning, Brand.WarningDot)
                else -> Triple(Brand.NeutralSoft, Brand.Neutral, Brand.NeutralDot)
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(soft)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
            ) {
                Box(Modifier.size(8.dp).clip(RoundedCornerShape(99.dp)).background(dot))
                Text(
                    collectionStatusLabel(sent.status) +
                        if (sent.status == "PARTIAL") " — متبقي ${egp(sent.remaining)} ج.م" else "",
                    color = tone,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
    // Sent, or saved on the phone and waiting for the internet (shown in «محفوظ على الهاتف»).
    val closed = account.days.mapNotNull { it.closeout?.shiftId }.toSet() +
        state.entries.filter { it.kind == EntryKind.CLOSEOUT && it.state != EntryState.FAILED }.map { it.shiftId }
    state.today
        .filter { it.status == "COMPLETED" && it.id !in closed }
        .forEach { shift ->
            GdCard {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    IconTile(R.drawable.ic_alert, Brand.WarningSoft, Brand.Warning, size = 44.dp, shape = RoundedCornerShape(14.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("تقفيل الوردية لم يُرسل", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        Text(
                            "${shift.vehicle.plateNumber} · انتهت ${formatTime(shift.endedAt)}",
                            fontSize = 12.sp,
                            color = Brand.InkMuted,
                        )
                    }
                }
                PrimaryButton("إرسال تقفيل الوردية", { vm.openCloseout(shift) }, enabled = !state.busy, height = 52.dp)
            }
        }
}

/** «حسابي مع الإدارة» summary; opens the full account. */
@Composable
private fun AccountCard(state: UiState, vm: MainViewModel) {
    val account = state.account ?: return
    val lastCollection = account.days
        .flatMap { day -> day.closeout?.collections.orEmpty() + listOfNotNull(day.collection) }
        .maxByOrNull { it.collectedAt }
    val shape = RoundedCornerShape(20.dp)
    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Brand.Surface)
            .border(1.dp, Brand.Line, shape)
            .clickable(role = Role.Button, onClickLabel = "فتح التفاصيل") { vm.showAccount(true) }
            .padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("حسابي مع الإدارة", fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            Text("التفاصيل", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Brand.Forest)
            Icon(
                painterResource(R.drawable.ic_chevron_start),
                contentDescription = null,
                tint = Brand.Forest,
                modifier = Modifier.size(16.dp),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(
                verticalArrangement = Arrangement.spacedBy(2.dp),
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Brand.SuccessSoft)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
            ) {
                Text(
                    lastCollection?.let { "تم التحصيل · ${formatTime(it.collectedAt)}" } ?: "تم التحصيل",
                    fontSize = 11.sp,
                    color = Brand.Success,
                )
                Text(
                    lastCollection?.let { "${egp(it.amount)} ج.م" } ?: "—",
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                    color = Brand.Success,
                )
            }
            Column(
                verticalArrangement = Arrangement.spacedBy(2.dp),
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Brand.DangerSoft)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
            ) {
                Text("متبقي لم يُحصَّل", fontSize = 11.sp, color = Brand.Danger)
                Text("${egp(account.outstanding)} ج.م", fontSize = 17.sp, fontWeight = FontWeight.Bold, color = Brand.Danger)
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
