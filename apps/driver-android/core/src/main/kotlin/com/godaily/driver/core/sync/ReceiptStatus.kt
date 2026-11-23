package com.godaily.driver.core.sync

/**
 * Where a queued entry's receipt photo stands (U30), for the driver's list.
 *
 * A receipt is uploaded only after its entry was accepted. Temporary network
 * failures leave it [WAITING] and it is retried automatically; a receipt the
 * server refused, or whose file is gone, is [REFUSED] with the reason and
 * stays on the list until the driver hides it, so a missing receipt is never
 * silent.
 */
enum class ReceiptStatus {
    /** The entry has no receipt photo. */
    NONE,

    /** Kept on the phone; uploads after the entry is accepted, retried on failure. */
    WAITING,

    /** Uploaded to the office. */
    UPLOADED,

    /** Not accepted (or the file is gone); [QueuedEntry.lastError] says why. */
    REFUSED,
}

fun QueuedEntry.receiptStatus(): ReceiptStatus = when {
    receiptPath == null -> ReceiptStatus.NONE
    !receiptDone -> ReceiptStatus.WAITING
    // After acceptance the last error is cleared, so one set now is the receipt's.
    state == EntryState.SYNCED && lastError != null -> ReceiptStatus.REFUSED
    else -> ReceiptStatus.UPLOADED
}

/** Entries the driver still needs to see: not yet accepted, refused, or with a receipt pending or refused. */
fun QueuedEntry.needsAttention(): Boolean =
    state != EntryState.SYNCED ||
        receiptStatus() == ReceiptStatus.WAITING ||
        receiptStatus() == ReceiptStatus.REFUSED
