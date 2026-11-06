package com.godaily.driver.core.api

/**
 * Failure of an API call, classified for retry decisions.
 *
 * The server's error envelope is `{"error": {"code", "message", "details"}}`
 * with an Arabic `message` that can be shown to the driver as is.
 */
sealed class ApiError(message: String, cause: Throwable? = null) : Exception(message, cause) {
    /** True when the same request may succeed later without changes. */
    abstract val retryable: Boolean

    /** No response: offline, DNS, timeout, TLS or connection reset. */
    class Network(cause: Throwable) : ApiError("تعذر الاتصال بالخادم", cause) {
        override val retryable = true
    }

    /** Token missing, expired or revoked: the driver must log in again. */
    class Unauthorized(val code: String, message: String) : ApiError(message) {
        override val retryable = false
    }

    /** 5xx or 429: the server is unavailable or throttling. */
    class Server(val status: Int, val code: String, message: String) : ApiError(message) {
        override val retryable = true
    }

    /** Any other 4xx: the request itself is not acceptable as sent. */
    class Rejected(
        val status: Int,
        val code: String,
        message: String,
        val fieldErrors: Map<String, String> = emptyMap(),
    ) : ApiError(message) {
        override val retryable = false
    }
}
