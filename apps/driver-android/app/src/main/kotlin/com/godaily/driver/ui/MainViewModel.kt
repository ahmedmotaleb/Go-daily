package com.godaily.driver.ui

import android.app.Application
import android.net.Uri
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.godaily.driver.container
import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.CashAccount
import com.godaily.driver.core.api.DayOffRequest
import com.godaily.driver.core.api.DriverCatalog
import com.godaily.driver.core.api.DriverMe
import com.godaily.driver.core.api.DriverVehicle
import com.godaily.driver.core.api.FuelEntryRequest
import com.godaily.driver.core.api.LoginRequest
import com.godaily.driver.core.api.Shift
import com.godaily.driver.core.api.StartSessionRequest
import com.godaily.driver.core.api.StartShiftRequest
import com.godaily.driver.core.cash.CloseoutCheck
import com.godaily.driver.core.cash.CloseoutDraft
import com.godaily.driver.core.cash.checkCloseout
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

    data object DayOff : Dialog

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
    /** The "حالة التتبع" screen is open over the home screen. */
    val showTracking: Boolean = false,
    /** «حسابي مع الإدارة», today's day-off and close-out (null until loaded). */
    val account: CashAccount? = null,
    val showAccount: Boolean = false,
    /** The shift whose close-out screen is open (active, or ended without a close-out). */
    val closeoutShift: Shift? = null,
    val closeoutDraft: CloseoutDraft = CloseoutDraft(),
    val closeoutErrors: Map<String, String> = emptyMap(),
    /** The last close-out attempt failed for lack of internet: offer ending the shift only. */
    val closeoutOffline: Boolean = false,
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
    private var dayOffKey: String? = null
    private var closeoutKey: String? = null
    private var closeoutKeyShiftId: String? = null

    // The start photo is uploaded once per capture, so a retried start sends the same id.
    private var startPhoto: Pair<Uri, String>? = null

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
                    // The account is secondary: the home screen works without it.
                    val account = async {
                        try {
                            c.api.account()
                        } catch (e: ApiError) {
                            if (e is ApiError.Unauthorized) throw e
                            null
                        }
                    }
                    val driver = me.await()
                    _state.update {
                        it.copy(
                            me = driver,
                            driverName = driver.fullName,
                            catalog = catalog.await(),
                            today = today.await(),
                            active = driver.activeShift,
                            account = account.await() ?: it.account,
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

    fun openDayOff() {
        dayOffKey = UUID.randomUUID().toString()
        _state.update { it.copy(dialog = Dialog.DayOff, dialogError = null) }
    }

    fun showAccount(show: Boolean) = _state.update { it.copy(showAccount = show) }

    /** «إنهاء وتقفيل الوردية» for the running shift, or a close-out still missing for an ended one. */
    fun openCloseout(shift: Shift) {
        // Same shift, same key: a retry after a lost response replays instead of failing.
        if (closeoutKeyShiftId != shift.id) {
            closeoutKey = UUID.randomUUID().toString()
            closeoutKeyShiftId = shift.id
        }
        _state.update {
            it.copy(
                closeoutShift = shift,
                closeoutErrors = emptyMap(),
                closeoutOffline = false,
            )
        }
    }

    fun closeCloseout() = _state.update { it.copy(closeoutShift = null, closeoutErrors = emptyMap()) }

    fun editCloseout(draft: CloseoutDraft) = _state.update { it.copy(closeoutDraft = draft) }

    fun registerDayOff(note: String) {
        val key = dayOffKey ?: UUID.randomUUID().toString().also { dayOffKey = it }
        busy {
            try {
                c.api.registerDayOff(DayOffRequest(note.trim().ifEmpty { null }), key)
                dayOffKey = null
                _state.update { it.copy(dialog = null, message = "تم تسجيل اليوم إجازة وظهر للإدارة") }
                refresh()
            } catch (e: ApiError) {
                _state.update { it.copy(dialogError = e.message) }
            }
        }
    }

    fun cancelDayOff() {
        busy {
            try {
                c.api.cancelDayOff()
                _state.update { it.copy(message = "تم إلغاء الإجازة") }
                refresh()
            } catch (e: ApiError) {
                _state.update { it.copy(message = e.message) }
            }
        }
    }

    fun submitCloseout(receipt: Uri?) {
        val st = _state.value
        val shift = st.closeoutShift ?: return
        val fixedEnd = if (shift.isActive) null else shift.endOdometerKm
        val request = when (val check = checkCloseout(st.closeoutDraft, shift.startOdometerKm, fixedEnd)) {
            is CloseoutCheck.Invalid -> {
                _state.update { it.copy(closeoutErrors = check.errors) }
                return
            }
            is CloseoutCheck.Valid -> check.request
        }
        val key = closeoutKey ?: UUID.randomUUID().toString().also { closeoutKey = it }
        val app = getApplication<Application>()
        busy {
            try {
                // Send the shift's queued points first so the path is complete when it ends.
                if (shift.isActive) c.syncer.syncNow()
                val closeout = c.api.submitCloseout(shift.id, request, key)
                closeoutKey = null
                if (shift.isActive) {
                    c.shiftState.clearActive()
                    TrackingController.stop(app)
                }
                var message = "تم إرسال تقفيل اليوم — التتبع متوقف"
                if (receipt != null) {
                    try {
                        c.api.uploadCloseoutReceipt(closeout.id, ReceiptPhotos.prepare(app, receipt))
                    } catch (e: CancellationException) {
                        throw e
                    } catch (_: Exception) {
                        message = "تم إرسال التقفيل، لكن تعذر رفع صورة الإيصال — سلّم الإيصال للمكتب"
                    } finally {
                        ReceiptPhotos.clearCache(app)
                    }
                }
                _state.update {
                    it.copy(
                        closeoutShift = null,
                        closeoutDraft = CloseoutDraft(),
                        closeoutErrors = emptyMap(),
                        closeoutOffline = false,
                        active = if (shift.isActive) null else it.active,
                        message = message,
                    )
                }
                refresh()
            } catch (e: ApiError.Network) {
                _state.update {
                    it.copy(
                        closeoutOffline = true,
                        closeoutErrors = mapOf("form" to "لا يوجد اتصال بالإنترنت — لم يُرسل التقفيل"),
                    )
                }
            } catch (e: ApiError.Rejected) {
                _state.update {
                    it.copy(closeoutErrors = e.fieldErrors.ifEmpty { mapOf("form" to (e.message ?: "")) })
                }
            } catch (e: ApiError) {
                _state.update { it.copy(closeoutErrors = mapOf("form" to (e.message ?: "تعذر الإرسال"))) }
            }
        }
    }

    /**
     * Offline: stop tracking and queue the shift end now; the close-out is sent
     * later from the home screen for that ended shift (the draft is kept).
     */
    fun endShiftWithoutCloseout() {
        val st = _state.value
        val shift = st.closeoutShift ?: return
        _state.update { it.copy(closeoutShift = null, closeoutOffline = false, closeoutErrors = emptyMap()) }
        if (shift.isActive) endShift(st.closeoutDraft.endOdometer, "")
    }

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
        photo: Uri?,
    ) {
        val reading = parseOdometer(odometer, vehicle.lastOdometerKm)
        if (reading is OdometerInput.Invalid) {
            _state.update { it.copy(dialogError = reading.message) }
            return
        }
        if (photo == null) {
            _state.update { it.copy(dialogError = "صوّر العداد أولًا لبدء الوردية") }
            return
        }
        val km = (reading as OdometerInput.Valid).km
        val key = startShiftKey ?: UUID.randomUUID().toString().also { startShiftKey = it }
        val app = getApplication<Application>()
        busy {
            try {
                val photoId = startPhoto?.takeIf { it.first == photo }?.second
                    ?: c.api.uploadOdometerPhoto(ReceiptPhotos.prepare(app, photo)).attachmentId
                        .also { startPhoto = photo to it }
                val shift = c.api.startShift(
                    StartShiftRequest(vehicle.id, km, planned?.id, operationTypeId, routeId, photoId),
                    key,
                )
                startShiftKey = null
                startPhoto = null
                ReceiptPhotos.clearCache(app)
                c.shiftState.setActive(shift)
                TrackingController.start(app)
                _state.update {
                    it.copy(active = shift, dialog = null, message = "بدأت الوردية — تتبع الموقع يعمل الآن")
                }
                refresh()
            } catch (e: IOException) {
                _state.update { it.copy(dialogError = e.message ?: "تعذر قراءة صورة العداد") }
            } catch (e: ApiError) {
                // A stale or refused photo is taken again on the next attempt.
                if (e is ApiError.Rejected) startPhoto = null
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

    fun showTracking(show: Boolean) = _state.update { it.copy(showTracking = show) }

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
