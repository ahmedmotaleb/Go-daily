package com.godaily.driver.ui.screens

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private val arabic: Locale = Locale.forLanguageTag("ar")

/** Display time is always Cairo time, whatever the phone's time zone. */
private val cairo: ZoneId = ZoneId.of("Africa/Cairo")

// java.time keeps Western digits by default (no DecimalStyle), matching the admin web.
private val timeFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("h:mm a", arabic)
private val longDate: DateTimeFormatter = DateTimeFormatter.ofPattern("EEEE d MMMM", arabic)

fun formatTime(instant: Instant?): String = instant?.atZone(cairo)?.format(timeFormat) ?: "—"

fun formatTimeMillis(millis: Long?): String = formatTime(millis?.let(Instant::ofEpochMilli))

/** «الأربعاء 5 نوفمبر» in Cairo. */
fun formatLongDate(millis: Long): String = Instant.ofEpochMilli(millis).atZone(cairo).format(longDate)

fun cairoHour(millis: Long): Int = Instant.ofEpochMilli(millis).atZone(cairo).hour

/** Shift timer «02:14:37». */
fun formatElapsed(millis: Long): String {
    val total = (millis / 1000).coerceAtLeast(0)
    return "%02d:%02d:%02d".format(Locale.ROOT, total / 3600, total % 3600 / 60, total % 60)
}

/** Kilometres with thousands separators: 184,320. */
fun formatKm(km: Int): String = "%,d".format(Locale.ROOT, km)

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
