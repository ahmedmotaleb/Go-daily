package com.godaily.driver.ui.screens

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.annotation.DrawableRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.R
import com.godaily.driver.core.text.ArabicText
import com.godaily.driver.core.tracking.CheckKind
import com.godaily.driver.core.tracking.CheckState
import com.godaily.driver.core.tracking.TrackingCheck
import com.godaily.driver.core.tracking.TrackingIssue
import com.godaily.driver.core.tracking.TrackingLevel
import com.godaily.driver.core.tracking.TrackingStatus
import com.godaily.driver.core.tracking.trackingChecks
import com.godaily.driver.ui.theme.Brand

/** Colours and icon for one tracking level (design: حالة التتبع). */
private data class LevelStyle(
    val dot: Color,
    val ring: Color,
    val text: Color,
    val soft: Color,
    val border: Color,
    @DrawableRes val icon: Int,
)

private fun styleOf(level: TrackingLevel): LevelStyle = when (level) {
    TrackingLevel.ACTIVE ->
        LevelStyle(Brand.Lime, Brand.SuccessSoft, Brand.Success, Brand.SuccessSoft, Color(0xFFCFE3A8), R.drawable.ic_location)
    TrackingLevel.UPLOADING ->
        LevelStyle(Brand.Forest, Brand.ActiveSoft, Brand.Forest, Brand.ActiveSoft, Brand.Line, R.drawable.ic_upload)
    TrackingLevel.OFFLINE_RECORDING ->
        LevelStyle(Brand.WarningDot, Brand.WarningSoft, Brand.Warning, Brand.WarningSoft, Color(0xFFF3D9A8), R.drawable.ic_wifi_off)
    TrackingLevel.WEAK_SIGNAL ->
        LevelStyle(Brand.WarningDot, Brand.WarningSoft, Brand.Warning, Brand.WarningSoft, Color(0xFFF3D9A8), R.drawable.ic_location)
    TrackingLevel.LOCATION_OFF, TrackingLevel.PERMISSION_REQUIRED, TrackingLevel.STOPPED ->
        LevelStyle(Brand.DangerDot, Brand.DangerSoft, Brand.Danger, Brand.DangerSoft, Color(0xFFF3C9C7), R.drawable.ic_alert)
    TrackingLevel.IDLE ->
        LevelStyle(Brand.NeutralDot, Brand.NeutralSoft, Brand.Neutral, Brand.NeutralSoft, Brand.Line, R.drawable.ic_location)
}

@Composable
private fun Dot(color: Color, ring: Color, ringWidth: Int = 4) {
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier.size((12 + ringWidth * 2).dp).clip(CircleShape).background(ring),
    ) { Box(Modifier.size(12.dp).clip(CircleShape).background(color)) }
}

/**
 * Tracking state on the dark home header. Always visible; tapping it opens
 * the full tracking screen with the requirements and how to fix each one.
 */
@Composable
fun TrackingPill(status: TrackingStatus?, nowMillis: Long, shiftEndedToday: Boolean, onOpen: () -> Unit) {
    val level = status?.level ?: TrackingLevel.IDLE
    val tracking = level != TrackingLevel.IDLE
    val (title, sub) = if (!tracking) {
        // IDLE is not a fault: no shift means no location is collected.
        (if (shiftEndedToday) ArabicText.level(level) else "لا توجد وردية الآن") to
            (if (shiftEndedToday) "توقف التتبع مع إنهاء الوردية" else "يبدأ التتبع تلقائيًا عند بدء الوردية")
    } else {
        val fix = status?.lastFixAtMillis
        ArabicText.level(level) to
            (fix?.let { "آخر موقع ${ArabicText.since((nowMillis - it).coerceAtLeast(0) / 1000)}" } ?: ArabicText.detail(level))
    }
    val accent = when (level) {
        TrackingLevel.ACTIVE, TrackingLevel.UPLOADING -> Brand.Lime
        TrackingLevel.OFFLINE_RECORDING, TrackingLevel.WEAK_SIGNAL -> Brand.WarningDot
        TrackingLevel.LOCATION_OFF, TrackingLevel.PERMISSION_REQUIRED, TrackingLevel.STOPPED -> Brand.DangerDot
        TrackingLevel.IDLE -> null
    }
    val shape = RoundedCornerShape(16.dp)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(accent?.copy(alpha = 0.14f) ?: Color.White.copy(alpha = 0.06f))
            .border(1.dp, accent?.copy(alpha = 0.45f) ?: Color.White.copy(alpha = 0.14f), shape)
            .clickable(role = Role.Button, onClickLabel = "عرض حالة التتبع", onClick = onOpen)
            .padding(horizontal = 14.dp, vertical = 12.dp)
            .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
    ) {
        Dot(accent ?: Brand.NeutralDot, accent?.copy(alpha = 0.25f) ?: Color.Transparent, ringWidth = 5)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(sub, color = if (accent == Brand.Lime) Brand.LimeText else Brand.OnDarkMuted, fontSize = 12.sp)
        }
        Icon(
            painterResource(R.drawable.ic_chevron_start),
            contentDescription = null,
            tint = Brand.OnDarkMuted,
            modifier = Modifier.size(18.dp),
        )
    }
}

/** Full tracking screen: current state, requirement checklist with fixes, and what each state means. */
@Composable
fun TrackingScreen(
    status: TrackingStatus?,
    onBack: () -> Unit,
    onRestart: () -> Unit,
    onPermissions: () -> Unit,
    onRetrySync: () -> Unit,
) {
    BackHandler(onBack = onBack)
    val context = LocalContext.current
    val level = status?.level ?: TrackingLevel.IDLE
    val style = styleOf(level)
    Column(Modifier.fillMaxSize().background(Brand.Page)) {
        // Forest strip under the status bar keeps light system icons readable on every screen.
        Box(Modifier.fillMaxWidth().background(Brand.Forest).statusBarsPadding())
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(64.dp)
                .background(Brand.Surface)
                .padding(horizontal = 12.dp),
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = "رجوع", tint = Brand.Ink)
            }
            Text("حالة التتبع", fontSize = 18.sp, fontWeight = FontWeight.Bold, modifier = Modifier.semantics { heading() })
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(Brand.Line))
        Column(
            verticalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(16.dp)
                .navigationBarsPadding(),
        ) {
            CurrentState(status, level, style, onRestart, onRetrySync)
            Checklist(trackingChecks(status), context, onPermissions)
            StatesGuide()
        }
    }
}

@Composable
private fun CurrentState(
    status: TrackingStatus?,
    level: TrackingLevel,
    style: LevelStyle,
    onRestart: () -> Unit,
    onRetrySync: () -> Unit,
) {
    val shape = RoundedCornerShape(20.dp)
    Column(
        verticalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Brand.Surface)
            .border(1.dp, style.border, shape)
            .padding(18.dp)
            .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            IconTile(style.icon, style.soft, style.text)
            Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(ArabicText.level(level), fontSize = 18.sp, fontWeight = FontWeight.Bold)
                Text(ArabicText.detail(level), fontSize = 13.sp, color = Brand.InkSoft)
            }
        }
        if (status != null) {
            Column(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(Brand.Page)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
            ) {
                InfoLine("مواقع في انتظار الرفع", status.pendingPoints.toString())
                if (level != TrackingLevel.IDLE) InfoLine("آخر موقع مسجّل", formatTimeMillis(status.lastFixAtMillis))
            }
        }
        if (level == TrackingLevel.STOPPED) {
            ForestButton("إعادة تشغيل التتبع", onRestart, height = 48.dp)
        }
        if (status != null && TrackingIssue.SYNC_BACKLOG in status.issues) {
            Text(ArabicText.issue(TrackingIssue.SYNC_BACKLOG), fontSize = 13.sp, color = Brand.InkSoft)
            SecondaryButton("إرسال الآن", onRetrySync, modifier = Modifier.fillMaxWidth(), height = 48.dp)
        }
        if (level == TrackingLevel.OFFLINE_RECORDING) {
            Text(
                "لا تحتاج لفعل أي شيء. لا تغلق التطبيق من قائمة التطبيقات المفتوحة.",
                fontSize = 13.sp,
                color = Brand.InkSoft,
            )
        }
    }
}

@Composable
private fun InfoLine(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, fontSize = 14.sp, color = Brand.InkSoft)
        Text(value, fontSize = 14.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun Checklist(checks: List<TrackingCheck>, context: Context, onPermissions: () -> Unit) {
    GdCard(padding = 16.dp) {
        Text("متطلبات التتبع", fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.semantics { heading() })
        checks.forEachIndexed { i, check ->
            val (soft, tone, icon) = when (check.state) {
                CheckState.OK -> Triple(Brand.SuccessSoft, Brand.Success, R.drawable.ic_check)
                CheckState.WARNING -> Triple(Brand.WarningSoft, Brand.Warning, R.drawable.ic_alert)
                CheckState.PROBLEM -> Triple(Brand.DangerSoft, Brand.Danger, R.drawable.ic_alert)
                CheckState.NOT_CHECKED -> Triple(Brand.NeutralSoft, Brand.Neutral, R.drawable.ic_info)
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    IconTile(icon, soft, tone, size = 28.dp, shape = CircleShape)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(ArabicText.checkTitle(check.kind), fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            ArabicText.checkState(check),
                            fontSize = 12.sp,
                            color = if (check.state == CheckState.OK || check.state == CheckState.NOT_CHECKED) Brand.InkMuted else tone,
                        )
                    }
                }
                fixFor(check, context, onPermissions)?.let { (label, action) ->
                    val critical = check.state == CheckState.PROBLEM
                    if (critical) {
                        ForestButton(label, action, height = 48.dp)
                    } else {
                        SecondaryButton(label, action, modifier = Modifier.fillMaxWidth(), height = 44.dp)
                    }
                }
            }
            if (i < checks.lastIndex) Box(Modifier.fillMaxWidth().height(1.dp).background(Brand.Divider))
        }
    }
}

/** The one action that fixes a requirement, or null when the driver has nothing to do. */
private fun fixFor(check: TrackingCheck, context: Context, onPermissions: () -> Unit): Pair<String, () -> Unit>? =
    if (check.state != CheckState.WARNING && check.state != CheckState.PROBLEM) {
        null
    } else {
        when (check.kind) {
            CheckKind.LOCATION_PERMISSION ->
                (if (check.state == CheckState.PROBLEM) "منح إذن الموقع" else "السماح طوال الوقت") to onPermissions
            CheckKind.PHONE_GPS -> if (check.issue == TrackingIssue.LOCATION_DISABLED) {
                "تشغيل الموقع" to { context.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) }
            } else {
                null // weak signal: nothing to press, it recovers outdoors
            }
            CheckKind.BATTERY -> "إعدادات البطارية" to {
                context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            }
            CheckKind.NOTIFICATIONS -> "إعدادات الإشعارات" to { openAppSettings(context) }
            CheckKind.INTERNET -> null // points are kept on the phone and sent later
        }
    }

private val GUIDE = listOf(
    TrackingLevel.ACTIVE,
    TrackingLevel.OFFLINE_RECORDING,
    TrackingLevel.UPLOADING,
    TrackingLevel.WEAK_SIGNAL,
    TrackingLevel.LOCATION_OFF,
    TrackingLevel.PERMISSION_REQUIRED,
    TrackingLevel.STOPPED,
)

@Composable
private fun StatesGuide() {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(
            "معنى كل حالة",
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 4.dp).semantics { heading() },
        )
        GUIDE.forEach { level ->
            val style = styleOf(level)
            val shape = RoundedCornerShape(16.dp)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(shape)
                    .background(Brand.Surface)
                    .border(1.dp, Brand.Line, shape)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
            ) {
                Dot(style.dot, style.ring)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(ArabicText.level(level), fontSize = 14.sp, fontWeight = FontWeight.Bold)
                    Text(ArabicText.detail(level), fontSize = 12.sp, color = Brand.InkMuted)
                }
            }
        }
    }
}

fun openAppSettings(context: Context) {
    context.startActivity(
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}
