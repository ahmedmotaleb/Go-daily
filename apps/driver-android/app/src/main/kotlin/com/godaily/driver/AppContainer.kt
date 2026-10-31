package com.godaily.driver

import android.content.Context
import android.os.Build
import com.godaily.driver.core.api.DeviceInfo
import com.godaily.driver.core.api.DriverApi
import com.godaily.driver.core.api.OkHttpDriverApi
import com.godaily.driver.core.sync.SyncEngine
import com.godaily.driver.data.QueueDatabase
import com.godaily.driver.data.ShiftStateStore
import com.godaily.driver.data.SqliteEventQueue
import com.godaily.driver.data.SqlitePointQueue
import com.godaily.driver.security.KeystoreTokenStore
import com.godaily.driver.sync.Syncer
import com.godaily.driver.tracking.DeviceState
import com.godaily.driver.tracking.TrackingHealth
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import okhttp3.OkHttpClient

/** Manual dependency wiring; one instance per process (see [GoDailyApp]). */
class AppContainer(context: Context) {
    private val app = context.applicationContext

    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val tokenStore = KeystoreTokenStore(app)
    val shiftState = ShiftStateStore(app)
    val device = DeviceState(app)

    private val database = QueueDatabase(app)
    val pointQueue = SqlitePointQueue(database)
    val eventQueue = SqliteEventQueue(database)

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .callTimeout(60, TimeUnit.SECONDS)
        .build()

    val api: DriverApi = OkHttpDriverApi(
        baseUrl = BuildConfig.API_BASE_URL,
        tokens = tokenStore,
        client = httpClient,
        userAgent = "GoDailyDriver/${BuildConfig.VERSION_NAME} (Android ${Build.VERSION.SDK_INT})",
    )

    private val engine = SyncEngine(
        api = api,
        points = pointQueue,
        events = eventQueue,
        pendingEnd = shiftState,
        device = { DeviceInfo(appVersion = BuildConfig.VERSION_NAME, batteryLevel = device.power().batteryPercent) },
    )

    val syncer = Syncer(engine, tokenStore, shiftState, pointQueue)
    val health = TrackingHealth(this)
}
