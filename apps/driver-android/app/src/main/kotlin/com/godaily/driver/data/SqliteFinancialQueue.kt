package com.godaily.driver.data

import android.content.ContentValues
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import com.godaily.driver.core.sync.EntryKind
import com.godaily.driver.core.sync.EntryState
import com.godaily.driver.core.sync.FinancialQueue
import com.godaily.driver.core.sync.QueuedEntry
import java.io.File
import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * SQLite implementation of the core [FinancialQueue] (U45).
 *
 * Entries are written before anything is sent, so a fuel entry or close-out
 * survives the app being closed or the phone restarting. Receipt photos are
 * files in the app's private storage, deleted once uploaded or refused.
 */
class SqliteFinancialQueue(private val database: QueueDatabase) : FinancialQueue {
    private val db: SQLiteDatabase get() = database.writableDatabase

    override suspend fun add(entry: QueuedEntry) = withContext(Dispatchers.IO) {
        val values = ContentValues().putAll(
            "client_id" to entry.clientId,
            "kind" to entry.kind.name,
            "shift_id" to entry.shiftId,
            "payload" to entry.payload,
            "title" to entry.title,
            "created_at" to entry.createdAt.toEpochMilli(),
            "state" to entry.state.name,
            "attempts" to entry.attempts,
            "last_error" to entry.lastError,
            "server_id" to entry.serverId,
            "receipt_path" to entry.receiptPath,
            "receipt_done" to if (entry.receiptDone) 1 else 0,
        )
        db.insertWithOnConflict("entries", null, values, SQLiteDatabase.CONFLICT_IGNORE)
        Unit
    }

    override suspend fun outstanding(): List<QueuedEntry> = query(
        "SELECT * FROM entries WHERE state = ? OR (state = ? AND receipt_done = 0) ORDER BY created_at",
        EntryState.PENDING.name,
        EntryState.SYNCED.name,
    )

    override suspend fun all(): List<QueuedEntry> = query("SELECT * FROM entries ORDER BY created_at DESC")

    override suspend fun markSynced(clientId: String, serverId: String) = update(
        clientId,
        "state" to EntryState.SYNCED.name,
        "server_id" to serverId,
        "last_error" to null,
    )

    override suspend fun markFailed(clientId: String, reason: String) = update(
        clientId,
        "state" to EntryState.FAILED.name,
        "last_error" to reason,
    )

    override suspend fun recordAttempt(clientId: String, reason: String) = withContext(Dispatchers.IO) {
        db.execSQL(
            "UPDATE entries SET attempts = attempts + 1, last_error = ? WHERE client_id = ?",
            arrayOf(reason, clientId),
        )
    }

    override suspend fun markReceiptDone(clientId: String, reason: String?) = withContext(Dispatchers.IO) {
        receiptPath(clientId)?.let { File(it).delete() }
        val values = ContentValues().putAll("receipt_done" to 1)
        if (reason != null) values.put("last_error", reason)
        db.update("entries", values, "client_id = ?", arrayOf(clientId))
        Unit
    }

    override suspend fun remove(clientId: String) = withContext(Dispatchers.IO) {
        receiptPath(clientId)?.let { File(it).delete() }
        db.delete("entries", "client_id = ?", arrayOf(clientId))
        Unit
    }

    override suspend fun pruneSynced(before: Instant) = withContext(Dispatchers.IO) {
        db.delete(
            "entries",
            "state = ? AND receipt_done = 1 AND created_at < ?",
            arrayOf(EntryState.SYNCED.name, before.toEpochMilli().toString()),
        )
        Unit
    }

    private fun receiptPath(clientId: String): String? =
        db.rawQuery("SELECT receipt_path FROM entries WHERE client_id = ?", arrayOf(clientId)).use {
            if (it.moveToFirst() && !it.isNull(0)) it.getString(0) else null
        }

    private suspend fun update(clientId: String, vararg pairs: Pair<String, Any?>) = withContext(Dispatchers.IO) {
        db.update("entries", ContentValues().putAll(*pairs), "client_id = ?", arrayOf(clientId))
        Unit
    }

    private suspend fun query(sql: String, vararg args: String): List<QueuedEntry> = withContext(Dispatchers.IO) {
        db.rawQuery(sql, args).use { c -> buildList { while (c.moveToNext()) add(c.toEntry()) } }
    }

    private fun Cursor.toEntry(): QueuedEntry {
        fun str(name: String): String? = getColumnIndexOrThrow(name).let { if (isNull(it)) null else getString(it) }
        fun int(name: String): Int = getInt(getColumnIndexOrThrow(name))
        return QueuedEntry(
            clientId = str("client_id")!!,
            kind = EntryKind.valueOf(str("kind")!!),
            shiftId = str("shift_id")!!,
            payload = str("payload")!!,
            createdAt = Instant.ofEpochMilli(getLong(getColumnIndexOrThrow("created_at"))),
            title = str("title")!!,
            state = EntryState.valueOf(str("state")!!),
            attempts = int("attempts"),
            lastError = str("last_error"),
            serverId = str("server_id"),
            receiptPath = str("receipt_path"),
            receiptDone = int("receipt_done") == 1,
        )
    }
}
