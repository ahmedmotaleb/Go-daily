package com.godaily.driver.core.sync

import com.godaily.driver.core.api.ApiError
import com.godaily.driver.core.api.FuelEntryRequest
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/** U30: a receipt's state is always visible, and a refused one is never silent. */
class ReceiptStatusTest {
    private val t0 = Instant.parse("2026-11-07T08:00:00Z")

    private fun fuel(id: String, receipt: String?) = QueuedEntry.fuel(
        FuelEntryRequest(
            fuelTypeId = "cng",
            quantity = "20",
            totalAmount = "200",
            clientEntryId = id,
            shiftId = "s-1",
            recordedAt = t0.toString(),
        ),
        "غاز طبيعي 20 — 200 ج.م",
        receipt,
        t0,
    )

    private suspend fun entry(queue: InMemoryFinancialQueue, id: String) = queue.all().first { it.clientId == id }

    @Test
    fun `no receipt, waiting, uploaded`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(fuel("plain", null))
        queue.add(fuel("with", "/r/1.jpg"))
        assertEquals(ReceiptStatus.NONE, entry(queue, "plain").receiptStatus())
        assertEquals(ReceiptStatus.WAITING, entry(queue, "with").receiptStatus())

        // Offline while uploading the photo: still waiting, retried later.
        sender.receiptFailure = ApiError.Network(IOException("offline"))
        runCatching { FinancialSync(sender, queue) { byteArrayOf(1, 2, 3) }.run() }
        assertEquals(ReceiptStatus.WAITING, entry(queue, "with").receiptStatus())
        assertTrue(entry(queue, "with").needsAttention())

        sender.receiptFailure = null
        FinancialSync(sender, queue) { byteArrayOf(1, 2, 3) }.run()
        assertEquals(ReceiptStatus.UPLOADED, entry(queue, "with").receiptStatus())
        assertFalse(entry(queue, "with").needsAttention())
        assertFalse(entry(queue, "plain").needsAttention())
    }

    @Test
    fun `a refused or missing photo stays visible with the reason`() = runTest {
        val queue = InMemoryFinancialQueue()
        val sender = FakeSender()
        queue.add(fuel("refused", "/r/2.jpg"))
        queue.add(fuel("gone", "/r/3.jpg"))
        sender.receiptFailure = ApiError.Rejected(422, "unsupported_type", "نوع الملف غير مسموح")
        FinancialSync(sender, queue) { path -> if (path == "/r/3.jpg") null else byteArrayOf(1) }.run()

        val refused = entry(queue, "refused")
        assertEquals(ReceiptStatus.REFUSED, refused.receiptStatus())
        assertEquals("نوع الملف غير مسموح", refused.lastError)
        assertTrue(refused.needsAttention())

        val gone = entry(queue, "gone")
        assertEquals(ReceiptStatus.REFUSED, gone.receiptStatus())
        assertTrue(gone.lastError!!.contains("سلّم الإيصال"))
        // Neither is retried: the entry itself was accepted.
        assertTrue(queue.outstanding().isEmpty())
    }
}
