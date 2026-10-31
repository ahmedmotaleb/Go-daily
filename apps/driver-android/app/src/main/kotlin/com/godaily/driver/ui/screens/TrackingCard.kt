package com.godaily.driver.ui.screens

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.godaily.driver.core.text.ArabicText
import com.godaily.driver.core.tracking.TrackingIssue
import com.godaily.driver.core.tracking.TrackingLevel
import com.godaily.driver.core.tracking.TrackingStatus
import com.godaily.driver.ui.theme.Brand

/**
 * Always-visible tracking state: the driver can tell at a glance whether
 * the shift is being recorded, recorded offline, blocked or stopped.
 */
@Composable
fun TrackingCard(
    status: TrackingStatus?,
    onRestart: () -> Unit,
    onPermissions: () -> Unit,
    onRetrySync: () -> Unit,
) {
    val level = status?.level ?: TrackingLevel.IDLE
    val (container, content) = when (level) {
        TrackingLevel.ACTIVE -> Brand.Lime100 to Brand.Forest800
        TrackingLevel.IDLE -> Brand.Neutral100 to Brand.Neutral600
        TrackingLevel.OFFLINE_RECORDING, TrackingLevel.WEAK_SIGNAL -> Brand.WarningSoft to Brand.Warning
        TrackingLevel.BLOCKED, TrackingLevel.STOPPED -> Brand.DangerSoft to Brand.Danger
    }
    val context = LocalContext.current
    Card(
        colors = CardDefaults.cardColors(containerColor = container),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                ArabicText.level(level),
                color = content,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
            if (status != null) {
                if (level != TrackingLevel.IDLE) {
                    Text("آخر موقع: ${formatTimeMillis(status.lastFixAtMillis)}", color = content)
                }
                Text(ArabicText.pending(status.pendingPoints), color = content)
                status.issues.filter { it != TrackingIssue.OFFLINE }.forEach { issue ->
                    IssueRow(issue, content, context, onRestart, onPermissions, onRetrySync)
                }
            }
        }
    }
}

@Composable
private fun IssueRow(
    issue: TrackingIssue,
    color: Color,
    context: Context,
    onRestart: () -> Unit,
    onPermissions: () -> Unit,
    onRetrySync: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("• ${ArabicText.issue(issue)}", color = color, style = MaterialTheme.typography.bodyMedium)
        val action: Pair<String, () -> Unit>? = when (issue) {
            TrackingIssue.LOCATION_PERMISSION_DENIED -> "منح إذن الموقع" to onPermissions
            TrackingIssue.BACKGROUND_PERMISSION_MISSING -> "السماح طوال الوقت" to onPermissions
            TrackingIssue.LOCATION_DISABLED -> "فتح إعدادات الموقع" to {
                context.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
            }
            TrackingIssue.SERVICE_NOT_RUNNING -> "إعادة تشغيل التتبع" to onRestart
            TrackingIssue.BATTERY_OPTIMIZED -> "إعدادات البطارية" to {
                context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            }
            TrackingIssue.NOTIFICATIONS_BLOCKED -> "إعدادات الإشعارات" to { openAppSettings(context) }
            TrackingIssue.SYNC_BACKLOG -> "إرسال الآن" to onRetrySync
            TrackingIssue.NO_RECENT_FIX, TrackingIssue.OFFLINE -> null
        }
        if (action != null) {
            OutlinedButton(onClick = action.second) { Text(action.first) }
        }
    }
}

fun openAppSettings(context: Context) {
    context.startActivity(
        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}
