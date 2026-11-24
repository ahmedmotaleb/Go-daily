package com.godaily.driver.data

import android.content.ContentValues
import android.database.sqlite.SQLiteDatabase
import com.godaily.driver.core.api.GoDailyJson
import com.godaily.driver.core.api.GpsPoint
import com.godaily.driver.core.api.TrackingEvent
import com.godaily.driver.core.sync.EventQueue
import com.godaily.driver.core.sync.PendingBatch
import com.godaily.driver.core.sync.PointQueue
import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** SQLite implementation of the core [PointQueue] contract. */
class SqlitePointQueue(private val database: QueueDatabase) : PointQueue {
    private val db: SQLiteDatabase get() = database.writableDatabase

    override suspend fun enqueue(shiftId: String, point: GpsPoint) = withContext(Dispatchers.IO) {
        val values = ContentValues().putAll(
            "client_point_id" to point.clientPointId,
            "shift_id" to shiftId,
            "recorded_at" to point.recordedAt.toEpochMilli(),
            "payload" to GoDailyJson.encodeToString(GpsPoint.serializer(), point),
            "created_at" to System.currentTimeMillis(),
        )
        db.insertWithOnConflict("points", null, values, SQLiteDatabase.CONFLICT_IGNORE)
        Unit
    }

    override suspend fun inFlightBatch(): PendingBatch? = withContext(Dispatchers.IO) {
        val batchId = db.rawQuery(
            "SELECT batch_id FROM points WHERE batch_id IS NOT NULL AND failed_reason IS NULL ORDER BY id LIMIT 1",
            null,
        ).use { if (it.moveToFirst()) it.getString(0) else null } ?: return@withContext null
        loadBatch(batchId)
    }

    override suspend fun claimBatch(batchId: String, limit: Int): PendingBatch? = withContext(Dispatchers.IO) {
        db.beginTransaction()
        try {
            val shiftId = db.rawQuery(
                "SELECT shift_id FROM points WHERE batch_id IS NULL AND failed_reason IS NULL " +
                    "ORDER BY recorded_at, id LIMIT 1",
                null,
            ).use { if (it.moveToFirst()) it.getString(0) else null }
            if (shiftId == null) {
                db.setTransactionSuccessful()
                return@withContext null
            }
            db.execSQL(
                "UPDATE points SET batch_id = ? WHERE id IN (" +
                    "SELECT id FROM points WHERE batch_id IS NULL AND failed_reason IS NULL AND shift_id = ? " +
                    "ORDER BY recorded_at, id LIMIT ?)",
                arrayOf<Any>(batchId, shiftId, limit),
            )
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        loadBatch(batchId)
    }

    override suspend fun acknowledge(batchId: String) = withContext(Dispatchers.IO) {
        db.delete("points", "batch_id = ? AND failed_reason IS NULL", arrayOf(batchId))
        Unit
    }

    override suspend fun markFailed(batchId: String, reason: String) = withContext(Dispatchers.IO) {
        db.update("points", ContentValues().putAll("failed_reason" to reason), "batch_id = ?", arrayOf(batchId))
        Unit
    }

    override suspend fun pendingCount(): Int = withContext(Dispatchers.IO) {
        db.rawQuery("SELECT COUNT(*) FROM points WHERE failed_reason IS NULL", null)
            .use { if (it.moveToFirst()) it.getInt(0) else 0 }
    }

    override suspend fun oldestPendingAt(): Instant? = withContext(Dispatchers.IO) {
        db.rawQuery("SELECT MIN(recorded_at) FROM points WHERE failed_reason IS NULL", null).use {
            if (it.moveToFirst() && !it.isNull(0)) Instant.ofEpochMilli(it.getLong(0)) else null
        }
    }

    suspend fun failedCount(): Int = withContext(Dispatchers.IO) {
        db.rawQuery("SELECT COUNT(*) FROM points WHERE failed_reason IS NOT NULL", null)
            .use { if (it.moveToFirst()) it.getInt(0) else 0 }
    }

    /** Failed points are kept briefly for diagnosis, then removed. */
    suspend fun pruneFailed(olderThan: Instant) = withContext(Dispatchers.IO) {
        db.delete(
            "points",
            "failed_reason IS NOT NULL AND created_at < ?",
            arrayOf(olderThan.toEpochMilli().toString()),
        )
        Unit
    }

    private fun loadBatch(batchId: String): PendingBatch? {
        var shiftId: String? = null
        val points = mutableListOf<GpsPoint>()
        db.rawQuery(
            "SELECT shift_id, payload FROM points WHERE batch_id = ? ORDER BY recorded_at, id",
            arrayOf(batchId),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                shiftId = cursor.getString(0)
                points += GoDailyJson.decodeFromString(GpsPoint.serializer(), cursor.getString(1))
            }
        }
        val shift = shiftId ?: return null
        return PendingBatch(batchId, shift, points)
    }
}

class SqliteEventQueue(private val database: QueueDatabase) : EventQueue {
    private val db: SQLiteDatabase get() = database.writableDatabase

    override suspend fun enqueue(event: TrackingEvent) = withContext(Dispatchers.IO) {
        val values = ContentValues().putAll(
            "client_event_id" to event.clientEventId,
            "payload" to GoDailyJson.encodeToString(TrackingEvent.serializer(), event),
            "created_at" to System.currentTimeMillis(),
        )
        db.insertWithOnConflict("events", null, values, SQLiteDatabase.CONFLICT_IGNORE)
        Unit
    }

    override suspend fun pending(limit: Int): List<TrackingEvent> = withContext(Dispatchers.IO) {
        db.rawQuery("SELECT payload FROM events ORDER BY created_at LIMIT ?", arrayOf(limit.toString())).use {
            buildList {
                while (it.moveToNext()) add(GoDailyJson.decodeFromString(TrackingEvent.serializer(), it.getString(0)))
            }
        }
    }

    override suspend fun remove(clientEventIds: Collection<String>) = withContext(Dispatchers.IO) {
        if (clientEventIds.isEmpty()) return@withContext
        db.beginTransaction()
        try {
            for (id in clientEventIds) db.delete("events", "client_event_id = ?", arrayOf(id))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }
}
