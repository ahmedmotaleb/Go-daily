package com.godaily.driver.ui.screens

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val arabic: Locale = Locale.forLanguageTag("ar")
private val timeFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("h:mm a", arabic)

/** Local time with Western digits (matching the admin web). */
fun formatTime(instant: Instant?): String =
    instant?.atZone(ZoneId.systemDefault())?.format(timeFormat) ?: "—"

fun formatTimeMillis(millis: Long?): String = formatTime(millis?.let(Instant::ofEpochMilli))

fun formatDuration(minutes: Int?): String {
    if (minutes == null) return "—"
    val h = minutes / 60
    val m = minutes % 60
    return when {
        h == 0 -> "$m دقيقة"
        m == 0 -> "$h ساعة"
        else -> "$h ساعة و$m دقيقة"
    }
}
