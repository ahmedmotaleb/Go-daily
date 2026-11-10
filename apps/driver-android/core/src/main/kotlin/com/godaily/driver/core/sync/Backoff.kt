package com.godaily.driver.core.sync

import kotlin.math.min
import kotlin.random.Random
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds

/**
 * Exponential backoff with full jitter: attempt n waits a random time in
 * [0, min(cap, base * 2^n)]. Jitter spreads retries from many phones that
 * regain connectivity at the same moment (e.g. leaving a tunnel together).
 */
class Backoff(
    private val base: Duration = 5.seconds,
    private val cap: Duration = 15.minutes,
    private val random: Random = Random.Default,
) {
    init {
        require(base.isPositive() && cap >= base) { "invalid backoff bounds" }
    }

    fun delayFor(attempt: Int): Duration {
        require(attempt >= 0) { "attempt must be >= 0" }
        val exp = base.inWholeMilliseconds.toDouble() * (1L shl min(attempt, 30)).toDouble()
        val ceiling = min(exp, cap.inWholeMilliseconds.toDouble()).toLong()
        return random.nextLong(0, ceiling + 1).milliseconds
    }
}
