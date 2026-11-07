package com.godaily.driver.core.sync

import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.CloseoutRequest
import com.godaily.driver.core.api.FuelEntryRequest
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class InMemoryFinancialQueue : FinancialQueue {
    val rows = linkedMapOf<String, QueuedEntry>()

    override suspend fun add(entry: QueuedEntry) {
        rows.putIfAbsent(entry.clientId, entry)
    }

    override suspend fun outstanding() = rows.values
        .filter { it.state == EntryState.PENDING || (it.state == EntryState.SYNCED && !it.receiptDone) }
        .sortedBy { it.createdAt }

    override suspend fun all() = rows.values.sortedByDescending { it.createdAt }

    private fun update(id: String, f: (QueuedEntry) -> QueuedEntry) {
        rows[id] = f(rows.getValue(id))
    }

    override suspend fun markSynced(clientId: String, serverId: String) =
        update(clientId) { it.copy(state = EntryState.SYNCED, serverId = serverId, lastError = null) }

    override suspend fun markFailed(clientId: String, reason: String) =
        update(clientId) { it.copy(state = EntryState.FAILED, lastError = reason) }

    override suspend fun recordAttempt(clientId: String, reason: String) =
        update(clientId) { it.copy(attempts = it.attempts + 1, lastError = reason) }

    override suspend fun markReceiptDone(clientId: String, reason: String?) =
        update(clientId) { it.copy(receiptDone = true, lastError = reason ?: it.lastError) }

    override suspend fun remove(clientId: String) {
        rows.remove(clientId)
    }

    override suspend fun pruneSynced(before: Instant) {
        rows.values.removeIf { it.state == EntryState.SYNCED && it.receiptDone && it.createdAt < before }
    }
}

/** A server that keeps one record per client id, like the real API. */
class FakeSender : FinancialSender {
    val failures = ArrayDeque<ApiError>()
    val records = linkedMapOf<String, String>()
    val keys = mutableListOf<String>()
    val receipts = mutableListOf<Pair<EntryKind, String>>()
    var receiptFailure: ApiError? = null

    private fun record(clientId: String?, key: String): String {
        failures.removeFirstOrNull()?.let { throw it }
        keys += key
        return records.getOrPut(clientId ?: key) { "srv-${records.size + 1}" }
    }

    override suspend fun sendFuel(request: FuelEntryRequest, idempotencyKey: String) =
        record(request.clientEntryId, idempotencyKey)

    override suspend fun sendCloseout(shiftId: String, request: CloseoutRequest, idempotencyKey: String) =
        record(request.clientEntryId, idempotencyKey)

    override suspend fun uploadReceipt(kind: EntryKind, serverId: String, image: ByteArray) {
        receiptFailure?.let { throw it }
        receipts += kind to serverId
    }
}

class FinancialSyncTest {
    private val t0 = Instant.parse("2026-11-07T08:00:00Z")

    private fun fuel(id: String, at: Instant = t0, receipt: String? = null) = QueuedEntry.fuel(
        FuelEntryRequest(
            fuelTypeId = "cng",
            quantity = "20",
            totalAmount = "200",
            clientEntryId = id,
            shiftId = "shift-1",
            recordedAt = at.toString(),
        ),
        title = "غاز طبيعي 20",
        receiptPath = receipt,
        now = at,
    )

    private fun closeout(id: String) = QueuedEntry.closeout(
        "shift-1",
        CloseoutRequest(endOdometerKm = 50_088, collectionAmount = "2940", tollAmount = "0", clientEntryId = id),
        title = "تقفيل الوردية",
        receiptPath = null,
        now = t0.plusSeconds(60),
    )

    @Test
    fun `entries are sent oldest first under their own id as key`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(closeout("c-1"))
        queue.add(fuel("f-1"))
        val report = FinancialSync(sender, queue) { null }.run()
        assertEquals(2, report.sent)
        assertEquals(listOf("f-1", "c-1"), sender.keys)
        assertTrue(queue.rows.values.all { it.state == EntryState.SYNCED })
        assertTrue(queue.outstanding().isEmpty())
    }

    @Test
    fun `a lost response and a resend never make a second record`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(fuel("f-1"))
        // Server stored it, but the phone saw a network error.
        sender.records["f-1"] = "srv-1"
        sender.failures += ApiError.Network(IOException("reset"))
        assertTrue(runCatching { FinancialSync(sender, queue) { null }.run() }.exceptionOrNull() is ApiError.Network)
        assertEquals(EntryState.PENDING, queue.rows.getValue("f-1").state)
        assertEquals(1, queue.rows.getValue("f-1").attempts)

        // Saving the same entry again (double tap, restart) does not add it twice.
        queue.add(fuel("f-1"))
        FinancialSync(sender, queue) { null }.run()
        assertEquals(1, sender.records.size)
        assertEquals("srv-1", queue.rows.getValue("f-1").serverId)
    }

    @Test
    fun `a refused entry is kept as failed and the others continue`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(fuel("f-1"))
        queue.add(fuel("f-2", t0.plusSeconds(30)))
        sender.failures += ApiError.Rejected(409, "already_closed_out", "تم إرسال تقفيل هذه الوردية بالفعل")
        val report = FinancialSync(sender, queue) { null }.run()
        assertEquals(1, report.failed)
        assertEquals(1, report.sent)
        val failed = queue.rows.getValue("f-1")
        assertEquals(EntryState.FAILED, failed.state)
        assertEquals("تم إرسال تقفيل هذه الوردية بالفعل", failed.lastError)
        // Failed entries are not resent.
        FinancialSync(sender, queue) { null }.run()
        assertEquals(listOf("f-2"), sender.keys)
    }

    @Test
    fun `the receipt is uploaded only after the entry was accepted`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(fuel("f-1", receipt = "/r/1.jpg"))
        sender.receiptFailure = ApiError.Network(IOException("offline"))
        assertTrue(runCatching { FinancialSync(sender, queue) { byteArrayOf(1) }.run() }.exceptionOrNull() is ApiError.Network)
        // Entry accepted; only the photo is left.
        val entry = queue.rows.getValue("f-1")
        assertEquals(EntryState.SYNCED, entry.state)
        assertEquals(listOf(entry), queue.outstanding())

        sender.receiptFailure = null
        val report = FinancialSync(sender, queue) { byteArrayOf(1) }.run()
        assertEquals(1, report.receipts)
        assertEquals(0, report.sent)
        assertEquals(listOf("f-1"), sender.keys) // the entry itself was sent once
        assertTrue(queue.outstanding().isEmpty())
    }

    @Test
    fun `a missing receipt file is reported instead of retried forever`() = runTest {
        val queue = InMemoryFinancialQueue()
        queue.add(fuel("f-1", receipt = "/gone.jpg"))
        FinancialSync(FakeSender(), queue) { null }.run()
        val entry = queue.rows.getValue("f-1")
        assertTrue(entry.receiptDone)
        assertTrue(entry.lastError!!.contains("سلّم الإيصال"))
    }

    @Test
    fun `pruning forgets only finished entries`() = runTest {
        val queue = InMemoryFinancialQueue()
        queue.add(fuel("f-1"))
        queue.add(fuel("f-2"))
        queue.markSynced("f-1", "srv-1")
        queue.pruneSynced(t0.plusSeconds(1))
        assertNull(queue.rows["f-1"])
        assertEquals(EntryState.PENDING, queue.rows.getValue("f-2").state)
    }

    @Test
    fun `the engine sends queued entries after a pending shift end`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(closeout("c-1"))
        val api = FakeDriverApi()
        val engine = SyncEngine(
            api = api,
            points = InMemoryPointQueue(),
            events = InMemoryEventQueue(),
            pendingEnd = InMemoryShiftEndStore(),
            financial = FinancialSync(sender, queue) { null },
        )
        val report = engine.run()
        assertEquals(SyncOutcome.COMPLETE, report.outcome)
        assertEquals(1, report.entriesSent)

        queue.add(fuel("f-1"))
        sender.failures += ApiError.Network(IOException("offline"))
        assertEquals(SyncOutcome.RETRY, engine.run().outcome)
    }
}
