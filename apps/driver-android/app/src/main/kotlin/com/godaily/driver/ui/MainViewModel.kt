package com.godaily.driver.ui

import android.app.Application
import android.net.Uri
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.godaily.driver.container
import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.DriverCatalog
import com.godaily.driver.core.api.DriverMe
import com.godaily.driver.core.api.DriverVehicle
import com.godaily.driver.core.api.FuelEntryRequest
import com.godaily.driver.core.api.LoginRequest
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.api.StartSessionRequest
import com.godaily.driver.core.api.StartShiftRequest
import com.godaily.driver.core.sync.PendingShiftEnd
import com.godaily.driver.core.text.DecimalInput
import com.godaily.driver.core.text.OdometerInput
import com.godaily.driver.core.text.normalizeDigits
import com.godaily.driver.core.text.parseOdometer
import com.godaily.driver.core.text.parsePositiveDecimal
import com.godaily.driver.core.tracking.TrackingStatus
import com.godaily.driver.receipt.ReceiptPhotos
import com.godaily.driver.sync.SyncScheduler
import com.godaily.driver.tracking.TrackingController
import com.godaily.driver.tracking.TrackingMonitor
import java.io.IOException
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

enum class Screen { LOADING, LOGIN, HOME }

sealed interface Dialog {
    data class StartShift(val planned: Shift?) : Dialog

    data object EndShift : Dialog

    data object ChangeOperation : Dialog

    data object RecordFuel : Dialog
}

data class UiState(
    val screen: Screen = Screen.LOADING,
    val driverName: String? = null,
    val me: DriverMe? = null,
    val catalog: DriverCatalog? = null,
    val today: List<Shift> = emptyList(),
    val active: Shift? = null,
    val tracking: TrackingStatus? = null,
    val pendingEnd: Boolean = false,
    val dialog: Dialog? = null,
    val showPermissions: Boolean = false,
    val busy: Boolean = false,
    val refreshing: Boolean = false,
    /** Last refresh failed for lack of connectivity: data may be outdated. */
    val stale: Boolean = false,
    val message: String? = null,
    val dialogError: String? = null,
    val loginError: String? = null,
    /** Fuel entry saved but its receipt photo did not upload: offer a retry. */
    val receiptRetry: ReceiptRetry? = null,
)

data class ReceiptRetry(val entryId: String, val photo: Uri)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val c = app.container
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state

    // One idempotency key per user intent, reused when the same action is
    // retried, so a lost response never creates a second shift or session.
    private var startShiftKey: String? = null
    private var sessionKey: String? = null
    private var fuelKey: String? = null

    init {
        if (c.tokenStore.isLoggedIn()) {
            _state.update {
                it.copy(screen = Screen.HOME, driverName = c.tokenStore.driverName, pendingEnd = hasPendingEnd())
            }
            refresh()
        } else {
            _state.update { it.copy(screen = Screen.LOGIN) }
        }
        viewModelScope.launch { TrackingMonitor.status.collect { s -> _state.update { it.copy(tracking = s) } } }
        viewModelScope.launch {
            c.syncer.sessionExpired.collect { expired -> if (expired) onSessionExpired() }
        }
        viewModelScope.launch {
            c.syncer.lastReport.collect { report ->
                if (report == null) return@collect
                _state.update { it.copy(pendingEnd = hasPendingEnd()) }
                when {
                    report.endedShift != null -> {
                        _state.update { it.copy(message = "تم إنهاء الوردية وإرسال بياناتها") }
                        refresh()
                    }
                    report.shiftEndError != null -> {
                        _state.update { it.copy(message = report.shiftEndError) }
                        refresh()
                    }
                }
            }
        }
    }

    private fun hasPendingEnd() = c.shiftState.pendingEndShiftId != null

    /** Re-evaluates tracking health while the app is visible. */
    fun checkTracking() {
        viewModelScope.launch { c.health.check() }
    }

    fun consumeMessage() = _state.update { it.copy(message = null) }

    fun login(phone: String, password: String) {
        if (phone.isBlank() || password.isEmpty()) {
            _state.update { it.copy(loginError = "أدخل رقم الهاتف وكلمة المرور") }
            return
        }
        busy {
            try {
                val res = c.api.login(
                    LoginRequest(phone = normalizeDigits(phone).trim(), password = password, deviceName = Build.MODEL),
                )
                c.tokenStore.save(res.accessToken, res.expiresAt, res.user.fullName)
                c.syncer.onLoggedIn()
                _state.update {
                    it.copy(screen = Screen.HOME, driverName = res.user.fullName, loginError = null)
                }
                refresh()
                SyncScheduler.syncSoon(getApplication())
            } catch (e: ApiError) {
                _state.update { it.copy(loginError = e.message) }
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(refreshing = true) }
            try {
                coroutineScope {
                    val me = async { c.api.me() }
                    val catalog = async { c.api.catalog() }
                    val today = async { c.api.todayShifts() }
                    val driver = me.await()
                    _state.update {
                        it.copy(
                            me = driver,
                            driverName = driver.fullName,
                            catalog = catalog.await(),
                            today = today.await(),
                            active = driver.activeShift,
                            stale = false,
                        )
                    }
                    reconcile(driver.activeShift)
                }
            } catch (_: ApiError.Unauthorized) {
                onSessionExpired()
            } catch (e: ApiError) {
                _state.update {
                    it.copy(stale = e is ApiError.Network, message = if (e is ApiError.Network) null else e.message)
                }
            } finally {
                _state.update { it.copy(refreshing = false, pendingEnd = hasPendingEnd()) }
            }
        }
    }

    /** Aligns the local work context (and tracking) with the server. */
    private fun reconcile(active: Shift?) {
        val app = getApplication<Application>()
        when {
            // Ended on the phone; the end request is queued. Do not resume tracking.
            active != null && active.id == c.shiftState.pendingEndShiftId -> Unit
            active != null -> {
                c.shiftState.setActive(active)
                if (c.device.hasFineLocation()) TrackingController.start(app)
            }
            c.shiftState.activeShiftId != null -> {
                // Ended or cancelled from the office.
                c.shiftState.clearActive()
                TrackingController.stop(app)
            }
        }
    }

    fun openStartShift(planned: Shift? = null) {
        if (!c.shiftState.disclosureAccepted || !c.device.hasFineLocation()) {
            _state.update { it.copy(showPermissions = true) }
            return
        }
        startShiftKey = UUID.randomUUID().toString()
        _state.update { it.copy(dialog = Dialog.StartShift(planned), dialogError = null) }
    }

    fun openEndShift() = _state.update { it.copy(dialog = Dialog.EndShift, dialogError = null) }

    fun openChangeOperation() {
        sessionKey = UUID.randomUUID().toString()
        _state.update { it.copy(dialog = Dialog.ChangeOperation, dialogError = null) }
    }

    fun openFuel() {
        fuelKey = UUID.randomUUID().toString()
        _state.update { it.copy(dialog = Dialog.RecordFuel, dialogError = null) }
    }

    fun closeDialog() {
        if (_state.value.dialog == Dialog.RecordFuel) ReceiptPhotos.clearCache(getApplication<Application>())
        _state.update { it.copy(dialog = null, dialogError = null, receiptRetry = null) }
    }

    fun showDialogError(message: String) = _state.update { it.copy(dialogError = message) }

    fun recordFuel(
        fuelTypeId: String?,
        quantity: String,
        total: String,
        odometer: String,
        paidByDriver: Boolean,
        receipt: Uri?,
    ) {
        if (fuelTypeId == null) {
            _state.update { it.copy(dialogError = "اختر نوع الوقود أو الزيت") }
            return
        }
        val qty = parsePositiveDecimal(quantity, 3, "الكمية")
        val amount = parsePositiveDecimal(total, 2, "المبلغ")
        val odometerKm = if (odometer.isBlank()) null else parseOdometer(odometer)
        val error = listOf(qty, amount).filterIsInstance<DecimalInput.Invalid>().firstOrNull()?.message
            ?: (odometerKm as? OdometerInput.Invalid)?.message
        if (error != null) {
            _state.update { it.copy(dialogError = error) }
            return
        }
        val key = fuelKey ?: UUID.randomUUID().toString().also { fuelKey = it }
        // Only a fix the tracking service recorded in the last two minutes:
        // where the phone is now (the station), never an older or guessed one.
        val position = TrackingMonitor.position.value?.freshAt(System.currentTimeMillis())
        busy {
            val entry = try {
                c.api.recordFuel(
                    FuelEntryRequest(
                        fuelTypeId = fuelTypeId,
                        quantity = (qty as DecimalInput.Valid).value,
                        totalAmount = (amount as DecimalInput.Valid).value,
                        odometerKm = (odometerKm as? OdometerInput.Valid)?.km,
                        paidBy = if (paidByDriver) "DRIVER" else "COMPANY",
                        latitude = position?.latitude,
                        longitude = position?.longitude,
                        locationAccuracyM = position?.accuracyM,
                    ),
                    key,
                )
            } catch (e: ApiError) {
                _state.update { it.copy(dialogError = e.message) }
                return@busy
            }
            fuelKey = null
            if (receipt == null) {
                closeDialog()
                _state.update { it.copy(message = "تم تسجيل الوقود — بانتظار مراجعة الإدارة") }
            } else {
                uploadReceipt(entry.id, receipt)
            }
        }
    }

    /** The entry is saved; try its receipt photo again. */
    fun retryReceipt() {
        val retry = _state.value.receiptRetry ?: return
        busy { uploadReceipt(retry.entryId, retry.photo) }
    }

    private suspend fun uploadReceipt(entryId: String, photo: Uri) {
        try {
            val result = c.api.uploadFuelReceipt(entryId, ReceiptPhotos.prepare(getApplication<Application>(), photo))
            closeDialog()
            val note = if (result.possibleDuplicate) " (الصورة مطابقة لإيصال سابق وستراجعها الإدارة)" else ""
            _state.update { it.copy(message = "تم تسجيل الوقود وإرفاق الإيصال — بانتظار مراجعة الإدارة$note") }
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            val reason = when (e) {
                is ApiError -> e.message
                is IOException -> e.message
                else -> null
            } ?: "تعذر رفع الصورة"
            _state.update {
                it.copy(
                    receiptRetry = ReceiptRetry(entryId, photo),
                    dialogError = "تم حفظ سجل الوقود، لكن لم تُرفع صورة الإيصال: $reason",
                )
            }
        }
    }

    fun startShift(
        vehicle: DriverVehicle,
        odometer: String,
        planned: Shift?,
        operationTypeId: String?,
        routeId: String?,
    ) {
        val reading = parseOdometer(odometer, vehicle.lastOdometerKm)
        if (reading is OdometerInput.Invalid) {
            _state.update { it.copy(dialogError = reading.message) }
            return
        }
        val km = (reading as OdometerInput.Valid).km
        val key = startShiftKey ?: UUID.randomUUID().toString().also { startShiftKey = it }
        busy {
            try {
                val shift = c.api.startShift(
                    StartShiftRequest(vehicle.id, km, planned?.id, operationTypeId, routeId),
                    key,
                )
                startShiftKey = null
                c.shiftState.setActive(shift)
                TrackingController.start(getApplication())
                _state.update {
                    it.copy(active = shift, dialog = null, message = "بدأت الوردية — تتبع الموقع يعمل الآن")
                }
                refresh()
            } catch (e: ApiError) {
                _state.update { it.copy(dialogError = e.message) }
            }
        }
    }

    fun endShift(odometer: String, notes: String) {
        val shift = _state.value.active ?: return
        val reading = parseOdometer(odometer, shift.startOdometerKm)
        if (reading is OdometerInput.Invalid) {
            _state.update { it.copy(dialogError = reading.message) }
            return
        }
        val km = (reading as OdometerInput.Valid).km
        val app = getApplication<Application>()
        // Durable first, then the work context ends: tracking stops now even
        // if the server cannot be reached yet. Queued points still upload.
        c.shiftState.savePendingEnd(
            PendingShiftEnd(shift.id, km, notes.trim().ifEmpty { null }, UUID.randomUUID().toString(), Instant.now()),
        )
        c.shiftState.clearActive()
        TrackingController.stop(app)
        _state.update { it.copy(dialog = null, pendingEnd = true, message = "جارٍ إنهاء الوردية…") }
        viewModelScope.launch {
            val report = c.syncer.syncNow()
            if (report.endedShift == null && report.shiftEndError == null) {
                SyncScheduler.syncSoon(app)
                _state.update {
                    it.copy(message = "لا يوجد اتصال — توقف التتبع وسيتم إرسال إنهاء الوردية تلقائيًا عند عودة الإنترنت")
                }
            }
        }
    }

    fun retrySync() {
        viewModelScope.launch {
            val report = c.syncer.syncNow()
            if (report.error is ApiError.Network) {
                _state.update { it.copy(message = "لا يوجد اتصال بالإنترنت حاليًا") }
            }
        }
    }

    fun startSession(operationTypeId: String?, routeId: String?) {
        val shift = _state.value.active ?: return
        if (operationTypeId == null) {
            _state.update { it.copy(dialogError = "اختر نوع التشغيل") }
            return
        }
        val key = sessionKey ?: UUID.randomUUID().toString().also { sessionKey = it }
        busy {
            try {
                c.api.startSession(shift.id, StartSessionRequest(operationTypeId, routeId), key)
                sessionKey = null
                _state.update { it.copy(dialog = null, message = "تم تغيير التشغيل الحالي") }
                refresh()
            } catch (e: ApiError) {
                _state.update { it.copy(dialogError = e.message) }
            }
        }
    }

    fun endSession() {
        val session = _state.value.active?.activeSession ?: return
        busy {
            try {
                c.api.endSession(session.id)
                _state.update { it.copy(message = "تم إنهاء التشغيل الحالي") }
                refresh()
            } catch (e: ApiError) {
                _state.update { it.copy(message = e.message) }
            }
        }
    }

    fun showPermissions(show: Boolean) = _state.update { it.copy(showPermissions = show) }

    fun acceptDisclosure() {
        c.shiftState.disclosureAccepted = true
    }

    /** Called when the permission flow finishes: resume tracking if a shift is active. */
    fun permissionsUpdated() {
        _state.update { it.copy(showPermissions = false) }
        if (c.shiftState.activeShiftId != null && c.device.hasFineLocation()) {
            TrackingController.start(getApplication())
        }
        checkTracking()
    }

    fun restartTracking() {
        if (c.shiftState.activeShiftId == null) return
        if (!c.device.hasFineLocation()) {
            _state.update { it.copy(showPermissions = true) }
            return
        }
        TrackingController.start(getApplication())
        checkTracking()
    }

    fun logout() {
        if (c.shiftState.activeShiftId != null || hasPendingEnd()) {
            _state.update { it.copy(message = "أنهِ الوردية وأرسل بياناتها قبل تسجيل الخروج") }
            return
        }
        busy {
            if (c.pointQueue.pendingCount() > 0) {
                _state.update { it.copy(message = "توجد نقاط لم تُرسل بعد. اتصل بالإنترنت ثم أعد المحاولة") }
                retrySync()
                return@busy
            }
            try {
                c.api.logout()
            } catch (_: ApiError) {
                // The session is dropped locally either way.
            }
            c.tokenStore.clear()
            _state.value = UiState(screen = Screen.LOGIN)
        }
    }

    private fun onSessionExpired() {
        // Tracking of an active shift continues and points stay queued;
        // they upload after the driver logs in again.
        c.tokenStore.clear()
        _state.update {
            it.copy(screen = Screen.LOGIN, loginError = "انتهت الجلسة. سجّل الدخول مرة أخرى لإرسال بيانات الوردية.")
        }
    }

    private fun busy(block: suspend () -> Unit) {
        if (_state.value.busy) return
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            try {
                block()
            } finally {
                _state.update { it.copy(busy = false) }
            }
        }
    }
}
