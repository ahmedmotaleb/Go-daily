package com.godaily.driver.tracking

import android.Manifest
import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.godaily.driver.MainActivity
import com.godaily.driver.R
import com.godaily.driver.core.text.ArabicText
import com.godaily.driver.core.tracking.TrackingStatus

object Notifications {
    private const val CHANNEL_TRACKING = "tracking"
    private const val CHANNEL_ALERTS = "alerts"
    const val TRACKING_ID = 1001
    private const val RESUME_ID = 1002

    fun createChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_TRACKING,
                context.getString(R.string.channel_tracking),
                NotificationManager.IMPORTANCE_LOW,
            ).apply { description = context.getString(R.string.channel_tracking_desc) },
        )
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ALERTS,
                context.getString(R.string.channel_alerts),
                NotificationManager.IMPORTANCE_HIGH,
            ).apply { description = context.getString(R.string.channel_alerts_desc) },
        )
    }

    /** The ongoing notification required for a location foreground service. */
    fun tracking(context: Context, status: TrackingStatus?): Notification {
        val text = status?.let { ArabicText.level(it.level) } ?: ArabicText.level(
            com.godaily.driver.core.tracking.TrackingLevel.ACTIVE,
        )
        val detail = status?.let { "$text\n${ArabicText.pending(it.pendingPoints)}" } ?: text
        return NotificationCompat.Builder(context, CHANNEL_TRACKING)
            .setSmallIcon(R.drawable.ic_stat_tracking)
            .setContentTitle(context.getString(R.string.notification_tracking_title))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(detail))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(openApp(context))
            .build()
    }

    @SuppressLint("MissingPermission") // checked by canPost()
    fun updateTracking(context: Context, status: TrackingStatus) {
        if (!canPost(context)) return
        NotificationManagerCompat.from(context).notify(TRACKING_ID, tracking(context, status))
    }

    /** Tracking could not (re)start in the background: ask the driver to open the app. */
    @SuppressLint("MissingPermission") // checked by canPost()
    fun showResumeTracking(context: Context) {
        if (!canPost(context)) return
        val notification = NotificationCompat.Builder(context, CHANNEL_ALERTS)
            .setSmallIcon(R.drawable.ic_stat_tracking)
            .setContentTitle(context.getString(R.string.notification_resume_title))
            .setContentText(context.getString(R.string.notification_resume_text))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openApp(context))
            .build()
        NotificationManagerCompat.from(context).notify(RESUME_ID, notification)
    }

    fun cancelResumeTracking(context: Context) = NotificationManagerCompat.from(context).cancel(RESUME_ID)

    private fun canPost(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        return NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    private fun openApp(context: Context): PendingIntent = PendingIntent.getActivity(
        context,
        0,
        Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
    )
}
