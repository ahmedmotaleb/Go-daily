package com.godaily.driver.tracking

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.location.Location
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Looper
import android.os.PowerManager
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.godaily.driver.container
import com.godaily.driver.core.api.TrackingEventType
import com.godaily.driver.core.sync.UploadScheduler
import com.godaily.driver.core.tracking.AdaptiveSampler
import com.godaily.driver.core.tracking.FixDeduplicator
import com.godaily.driver.core.tracking.LocationFix
import com.godaily.driver.core.tracking.SamplingConfig
import com.godaily.driver.core.tracking.toGpsPoint
import com.godaily.driver.sync.SyncScheduler
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import java.util.UUID
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Foreground service that records the vehicle's location during an active
 * work shift, with the ongoing notification Android requires.
 *
 * - Runs only while the local work context has an active shift; it stops
 *   itself otherwise and is stopped when the shift ends.
 * - Every fix is written to the on-device queue first, then uploaded in
 *   idempotent batches, so connectivity loss never loses points.
 * - Health problems (permission revoked, location switched off, no fixes)
 *   are shown in the notification and reported to the server as events.
 */
class LocationTrackingService : LifecycleService() {
    private val c by lazy { applicationContext.container }
    private lateinit var fused: FusedLocationProviderClient
    private val sampler = AdaptiveSampler()
    private val dedupe = FixDeduplicator()
    private val uploads = UploadScheduler()
    private var shiftId: String? = null
    private var ticker: Job? = null
    private var upload: Job? = null
    private var receiverRegistered = false
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var validatedNetwork = false

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val fixes = result.locations.map { it.toFix() }
            lifecycleScope.launch { fixes.forEach { record(it) } }
        }
    }

    private val systemReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                Intent.ACTION_BATTERY_CHANGED, PowerManager.ACTION_POWER_SAVE_MODE_CHANGED ->
                    sampler.onPowerChanged(c.device.power())?.let(::subscribe)
                LocationManager.PROVIDERS_CHANGED_ACTION -> lifecycleScope.launch { checkHealth() }
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        val active = c.shiftState.activeShiftId
        if (active == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (!c.device.hasFineLocation()) {
            // A location service cannot run without the permission; the
            // health check reports PERMISSION_DENIED for management.
            c.appScope.launch { c.health.check() }
            Notifications.showResumeTracking(this)
            stopSelf()
            return START_NOT_STICKY
        }
        if (!enterForeground()) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (shiftId != active) begin(active)
        return START_STICKY
    }

    private fun enterForeground(): Boolean = try {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
        } else {
            0
        }
        ServiceCompat.startForeground(
            this,
            Notifications.TRACKING_ID,
            Notifications.tracking(this, TrackingMonitor.status.value),
            type,
        )
        true
    } catch (_: RuntimeException) {
        // ForegroundServiceStartNotAllowedException (background start, API 31+)
        // or SecurityException (missing location permission, API 34+).
        Notifications.showResumeTracking(this)
        false
    }

    private fun begin(active: String) {
        shiftId = active
        val first = c.shiftState.markTrackingStarted(active)
        lifecycleScope.launch {
            c.health.record(if (first) TrackingEventType.TRACKING_STARTED else TrackingEventType.SERVICE_RESTARTED)
        }
        sampler.onPowerChanged(c.device.power())
        TrackingMonitor.serviceStarted(System.currentTimeMillis(), sampler.config.intervalMillis)
        subscribe(sampler.config)
        registerSystemReceivers()
        registerNetworkCallback()
        Notifications.cancelResumeTracking(this)
        ticker?.cancel()
        ticker = lifecycleScope.launch {
            while (isActive) {
                checkHealth()
                maybeUpload()
                delay(TICK_MILLIS)
            }
        }
    }

    private fun subscribe(config: SamplingConfig) {
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, config.intervalMillis)
            .setMinUpdateIntervalMillis(config.intervalMillis / 2)
            .setMaxUpdateDelayMillis(config.maxDelayMillis)
            .setWaitForAccurateLocation(false)
            .build()
        try {
            // Re-registering the same callback replaces the previous request.
            fused.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
            TrackingMonitor.intervalChanged(config.intervalMillis)
        } catch (_: SecurityException) {
            lifecycleScope.launch { checkHealth() }
        }
    }

    private suspend fun record(fix: LocationFix) {
        val shift = shiftId ?: return
        if (!dedupe.accept(fix)) return
        val point = fix.toGpsPoint(UUID.randomUUID().toString()) ?: return
        c.pointQueue.enqueue(shift, point)
        TrackingMonitor.fixReceived(System.currentTimeMillis())
        sampler.onFix(fix)?.let(::subscribe)
        maybeUpload()
    }

    private suspend fun maybeUpload() {
        if (upload?.isActive == true) return
        val now = System.currentTimeMillis()
        val pending = c.pointQueue.pendingCount()
        val oldest = c.pointQueue.oldestPendingAt()?.toEpochMilli()
        if (!uploads.isDue(now, pending, oldest, c.device.online())) return
        upload = lifecycleScope.launch {
            val report = c.syncer.syncNow()
            uploads.onResult(System.currentTimeMillis(), report)
        }
    }

    private suspend fun checkHealth() {
        val status = c.health.check()
        Notifications.updateTracking(this, status)
    }

    private fun registerSystemReceivers() {
        if (receiverRegistered) return
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_BATTERY_CHANGED)
            addAction(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED)
            addAction(LocationManager.PROVIDERS_CHANGED_ACTION)
        }
        ContextCompat.registerReceiver(this, systemReceiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
        receiverRegistered = true
    }

    private fun registerNetworkCallback() {
        if (networkCallback != null) return
        val cm = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                val validated = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                lifecycleScope.launch {
                    if (validated && !validatedNetwork) {
                        // Back online: send the backlog now instead of waiting out the backoff.
                        uploads.onConnectivityRegained()
                        maybeUpload()
                    }
                    validatedNetwork = validated
                }
            }

            override fun onLost(network: Network) {
                lifecycleScope.launch {
                    validatedNetwork = false
                    checkHealth()
                }
            }
        }
        cm.registerDefaultNetworkCallback(callback)
        networkCallback = callback
    }

    override fun onDestroy() {
        ticker?.cancel()
        fused.removeLocationUpdates(locationCallback)
        if (receiverRegistered) {
            unregisterReceiver(systemReceiver)
            receiverRegistered = false
        }
        networkCallback?.let { getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(it) }
        networkCallback = null
        TrackingMonitor.serviceStopped()
        val stoppedShift = shiftId
        if (stoppedShift != null) {
            val shiftEnded = c.shiftState.activeShiftId != stoppedShift
            // lifecycleScope is cancelled by super.onDestroy(): use the app scope.
            c.appScope.launch {
                c.health.record(
                    TrackingEventType.TRACKING_STOPPED,
                    shiftId = stoppedShift,
                    details = mapOf("reason" to if (shiftEnded) "shift_ended" else "service_stopped"),
                )
                c.health.check()
            }
        }
        SyncScheduler.syncSoon(this)
        super.onDestroy()
    }

    private fun Location.toFix() = LocationFix(
        timeMillis = time,
        latitude = latitude,
        longitude = longitude,
        accuracyM = if (hasAccuracy()) accuracy else null,
        speedMps = if (hasSpeed()) speed else null,
        bearingDeg = if (hasBearing()) bearing else null,
        altitudeM = if (hasAltitude()) altitude else null,
        provider = provider,
        isMock = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            isMock
        } else {
            @Suppress("DEPRECATION")
            isFromMockProvider
        },
    )

    private companion object {
        const val TICK_MILLIS = 15_000L
    }
}
