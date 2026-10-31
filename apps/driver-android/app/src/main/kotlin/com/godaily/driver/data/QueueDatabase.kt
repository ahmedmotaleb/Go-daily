package com.godaily.driver.data

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * On-device queue for GPS points and device events awaiting upload.
 *
 * Plain SQLite (no annotation processing) keeps the queue dependency-free.
 * Rows are deleted as soon as the server acknowledges them, so location
 * history does not accumulate on the phone.
 */
class QueueDatabase(context: Context) : SQLiteOpenHelper(context, NAME, null, VERSION) {
    override fun onConfigure(db: SQLiteDatabase) {
        db.enableWriteAheadLogging()
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_point_id TEXT NOT NULL UNIQUE,
                shift_id TEXT NOT NULL,
                recorded_at INTEGER NOT NULL,
                payload TEXT NOT NULL,
                batch_id TEXT,
                failed_reason TEXT,
                created_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
        db.execSQL("CREATE INDEX points_open ON points (failed_reason, batch_id, recorded_at)")
        db.execSQL("CREATE INDEX points_batch ON points (batch_id)")
        db.execSQL(
            """
            CREATE TABLE events (
                client_event_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """.trimIndent(),
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // Version 1 is the first schema. Future versions must migrate in
        // place: the queue may hold points that were never uploaded.
    }

    companion object {
        private const val NAME = "godaily-queue.db"
        private const val VERSION = 1
    }
}

internal fun ContentValues.putAll(vararg pairs: Pair<String, Any?>): ContentValues = apply {
    for ((key, value) in pairs) {
        when (value) {
            null -> putNull(key)
            is String -> put(key, value)
            is Long -> put(key, value)
            is Int -> put(key, value)
            else -> error("unsupported value type for $key")
        }
    }
}
