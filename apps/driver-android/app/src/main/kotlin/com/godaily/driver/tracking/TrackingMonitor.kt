package com.godaily.driver.tracking

import com.godaily.driver.core.tracking.LastPosition
import com.godaily.driver.core.tracking.TrackingStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

/** Process-wide view of the tracking service, shared with the UI. */
object TrackingMonitor {
    data class ServiceInfo(
        val running: Boolean = false,
        val sinceMillis: Long? = null,
        val lastFixAtMillis: Long? = null,
        val intervalMillis: Long = 10_000,
    )

    private val _service = MutableStateFlow(ServiceInfo())
    val service: StateFlow<ServiceInfo> = _service

    val status = MutableStateFlow<TrackingStatus?>(null)

    // Latest recorded in-shift fix, in memory only (attached to fuel entries if recent).
    private val _position = MutableStateFlow<LastPosition?>(null)
    val position: StateFlow<LastPosition?> = _position

    fun positionRecorded(position: LastPosition) {
        _position.value = position
    }

    fun serviceStarted(now: Long, intervalMillis: Long) =
        _service.update { ServiceInfo(running = true, sinceMillis = now, intervalMillis = intervalMillis) }

    fun intervalChanged(intervalMillis: Long) = _service.update { it.copy(intervalMillis = intervalMillis) }

    fun fixReceived(now: Long) = _service.update { it.copy(lastFixAtMillis = now) }

    fun serviceStopped() {
        _service.update { ServiceInfo() }
        _position.value = null
    }
}
