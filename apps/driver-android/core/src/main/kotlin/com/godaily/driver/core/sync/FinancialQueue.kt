package com.godaily.driver.core.sync

import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.CloseoutRequest
import com.godaily.driver.core.api.DriverApi
import com.godaily.driver.core.api.FuelEntryRequest
import com.godaily.driver.core.api.GoDailyJson
import java.time.Instant

enum class EntryKind { FUEL, CLOSEOUT }

enum class EntryState {
    /** Saved on the phone, not yet accepted by the server. */
    PENDING,

    /** Accepted by the server (it holds the record from now on). */
    SYNCED,

    /** Refused by the server as sent; kept on the phone with the reason, never resent. */
    FAILED,
}

/**
 * A fuel entry or close-out saved on the phone first (U45).
 *
 * [clientId] is generated once when the driver saves the entry and is sent
 * as both the client entry id and the Idempotency-Key, so however many times
 * the entry is resent (lost response, app restart, days offline) the server
 * keeps one record. [payload] is the request as JSON, fixed at save time.
 */
data class QueuedEntry(
    val clientId: String,
    val kind: EntryKind,
    val shiftId: String,
    val payload: String,
    val createdAt: Instant,
    /** Short Arabic summary for the list on the phone, e.g. «غاز طبيعي 20 — 200 ج.م». */
    val title: String,
    val state: EntryState = EntryState.PENDING,
    val attempts: Int = 0,
    val lastError: String? = null,
    val serverId: String? = null,
    /** Local file of a receipt photo to upload once the entry is accepted. */
    val receiptPath: String? = null,
    val receiptDone: Boolean = receiptPath == null,
) {
    companion object {
        fun fuel(request: FuelEntryRequest, title: String, receiptPath: String?, now: Instant): QueuedEntry {
            val id = requireNotNull(request.clientEntryId) { "clientEntryId is required" }
            return QueuedEntry(
                clientId = id,
                kind = EntryKind.FUEL,
                shiftId = requireNotNull(request.shiftId) { "shiftId is required" },
                payload = GoDailyJson.encodeToString(FuelEntryRequest.serializer(), request),
                createdAt = now,
                title = title,
                receiptPath = receiptPath,
            )
        }

        fun closeout(
            shiftId: String,
            request: CloseoutRequest,
            title: String,
            receiptPath: String?,
            now: Instant,
        ): QueuedEntry = QueuedEntry(
            clientId = requireNotNull(request.clientEntryId) { "clientEntryId is required" },
            kind = EntryKind.CLOSEOUT,
            shiftId = shiftId,
            payload = GoDailyJson.encodeToString(CloseoutRequest.serializer(), request),
            createdAt = now,
            title = title,
            receiptPath = receiptPath,
        )
    }
}

/** Durable store of [QueuedEntry] (SQLite on Android). */
interface FinancialQueue {
    /** Adds the entry; an entry with the same client id already stored is left as is. */
    suspend fun add(entry: QueuedEntry)

    /** Entries still to send, or accepted with a receipt still to upload; oldest first. */
    suspend fun outstanding(): List<QueuedEntry>

    /** Everything kept on the phone, newest first (for the driver's list). */
    suspend fun all(): List<QueuedEntry>

    suspend fun markSynced(clientId: String, serverId: String)

    suspend fun markFailed(clientId: String, reason: String)

    /** A temporary failure: counted, the entry stays pending. */
    suspend fun recordAttempt(clientId: String, reason: String)

    /** The receipt was uploaded, or refused (then [reason] says why). */
    suspend fun markReceiptDone(clientId: String, reason: String? = null)

    /** Removes an entry (one the driver dismissed, or refused while the form is still open). */
    suspend fun remove(clientId: String)

    /** Forgets accepted entries older than [before]; pending and failed ones are kept. */
    suspend fun pruneSynced(before: Instant)
}

/** The calls the queue needs; [ApiFinancialSender] maps them to [DriverApi]. */
interface FinancialSender {
    suspend fun sendFuel(request: FuelEntryRequest, idempotencyKey: String): String

    suspend fun sendCloseout(shiftId: String, request: CloseoutRequest, idempotencyKey: String): String

    suspend fun uploadReceipt(kind: EntryKind, serverId: String, image: ByteArray)
}

class ApiFinancialSender(private val api: DriverApi) : FinancialSender {
    override suspend fun sendFuel(request: FuelEntryRequest, idempotencyKey: String): String =
        api.recordFuel(request, idempotencyKey).id

    override suspend fun sendCloseout(shiftId: String, request: CloseoutRequest, idempotencyKey: String): String =
        api.submitCloseout(shiftId, request, idempotencyKey).id

    override suspend fun uploadReceipt(kind: EntryKind, serverId: String, image: ByteArray) {
        when (kind) {
            EntryKind.FUEL -> api.uploadFuelReceipt(serverId, image)
            EntryKind.CLOSEOUT -> api.uploadCloseoutReceipt(serverId, image)
        }
    }
}

data class FinancialReport(val sent: Int = 0, val failed: Int = 0, val receipts: Int = 0)

/**
 * Sends queued entries oldest first. A network or server failure stops the
 * run (the entry stays pending and is sent next time); a refusal marks only
 * that entry failed, with the server's Arabic reason, and the rest continue.
 * A receipt is uploaded only after its entry was accepted.
 */
class FinancialSync(
    private val sender: FinancialSender,
    private val queue: FinancialQueue,
    /** Reads a saved receipt photo; null when the file is gone. */
    private val receipts: suspend (String) -> ByteArray?,
) {
    suspend fun run(): FinancialReport {
        var sent = 0
        var failed = 0
        var uploaded = 0
        for (entry in queue.outstanding()) {
            var serverId = entry.serverId
            if (entry.state == EntryState.PENDING) {
                serverId = try {
                    send(entry)
                } catch (e: ApiError.Rejected) {
                    queue.markFailed(entry.clientId, e.message ?: e.code)
                    failed++
                    continue
                } catch (e: ApiError) {
                    if (e !is ApiError.Unauthorized) queue.recordAttempt(entry.clientId, e.message ?: "")
                    throw e
                }
                queue.markSynced(entry.clientId, serverId)
                sent++
            }
            val path = entry.receiptPath
            if (path != null && !entry.receiptDone && serverId != null) {
                if (uploadReceipt(entry, serverId, path)) uploaded++
            }
        }
        return FinancialReport(sent, failed, uploaded)
    }

    private suspend fun send(entry: QueuedEntry): String = when (entry.kind) {
        EntryKind.FUEL -> sender.sendFuel(
            GoDailyJson.decodeFromString(FuelEntryRequest.serializer(), entry.payload),
            entry.clientId,
        )
        EntryKind.CLOSEOUT -> sender.sendCloseout(
            entry.shiftId,
            GoDailyJson.decodeFromString(CloseoutRequest.serializer(), entry.payload),
            entry.clientId,
        )
    }

    private suspend fun uploadReceipt(entry: QueuedEntry, serverId: String, path: String): Boolean {
        val image = receipts(path)
        if (image == null) {
            queue.markReceiptDone(entry.clientId, "صورة الإيصال لم تعد موجودة على الهاتف — سلّم الإيصال للمكتب")
            return false
        }
        return try {
            sender.uploadReceipt(entry.kind, serverId, image)
            queue.markReceiptDone(entry.clientId)
            true
        } catch (e: ApiError.Rejected) {
            queue.markReceiptDone(entry.clientId, e.message ?: e.code)
            false
        }
    }
}
