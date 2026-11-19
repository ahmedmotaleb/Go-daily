package com.godaily.driver.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.godaily.driver.container
import com.godaily.driver.core.sync.SyncOutcome
import java.util.concurrent.TimeUnit

/**
 * Uploads the queue when the tracking service is not running: after the
 * shift ended with unsynced points, after a crash, or after a reboot.
 * WorkManager only runs it with a network and retries with backoff.
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val report = applicationContext.container.syncer.syncNow()
        return when (report.outcome) {
            SyncOutcome.COMPLETE -> Result.success()
            SyncOutcome.RETRY -> Result.retry()
            // Nothing can be sent until the driver logs in again.
            SyncOutcome.AUTH_REQUIRED -> Result.success()
        }
    }
}

object SyncScheduler {
    private const val PERIODIC = "gd-sync-periodic"
    private const val SOON = "gd-sync-soon"

    private val connected = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(connected)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
    }

    /** Upload as soon as there is a network (keeps an already-queued run). */
    fun syncSoon(context: Context) {
        val request = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(connected)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(SOON, ExistingWorkPolicy.KEEP, request)
    }
}
