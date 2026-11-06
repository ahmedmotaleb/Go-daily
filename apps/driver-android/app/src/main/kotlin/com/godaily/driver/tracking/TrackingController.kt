package com.godaily.driver.tracking

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.godaily.driver.container
import com.godaily.driver.sync.SyncScheduler

object TrackingController {
    /** Starts (or keeps) the tracking service for the active shift. */
    fun start(context: Context): Boolean = try {
        ContextCompat.startForegroundService(context, Intent(context, LocationTrackingService::class.java))
        Notifications.cancelResumeTracking(context)
        true
    } catch (_: IllegalStateException) {
        // Background start not allowed (Android 12+): the driver must open the app.
        Notifications.showResumeTracking(context)
        false
    }

    fun stop(context: Context) {
        context.stopService(Intent(context, LocationTrackingService::class.java))
    }
}

/**
 * Resumes tracking after a reboot or app update if a shift is still active.
 * Starting a location service from the background needs "allow all the
 * time"; without it the driver gets a notification to reopen the app.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val c = context.container
        SyncScheduler.syncSoon(context)
        if (c.shiftState.activeShiftId == null) return
        if (c.device.hasFineLocation() && c.device.hasBackgroundLocation()) {
            TrackingController.start(context)
        } else {
            Notifications.showResumeTracking(context)
        }
    }
}
