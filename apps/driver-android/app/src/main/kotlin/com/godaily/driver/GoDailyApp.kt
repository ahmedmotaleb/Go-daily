package com.godaily.driver

import android.app.Application
import android.content.Context
import com.godaily.driver.sync.SyncScheduler
import com.godaily.driver.tracking.Notifications

class GoDailyApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        Notifications.createChannels(this)
        SyncScheduler.schedulePeriodic(this)
    }
}

val Context.container: AppContainer get() = (applicationContext as GoDailyApp).container
