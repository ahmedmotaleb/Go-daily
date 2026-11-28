package com.godaily.driver.core.account

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class PasswordChangeTest {
    @Test
    fun `a valid change becomes the request the API expects`() {
        val check = checkPasswordChange("Staff-set-77", "My-own-pass-1", "My-own-pass-1")
        assertTrue(check is PasswordCheck.Valid, check.toString())
        val request = (check as PasswordCheck.Valid).request
        assertEquals("Staff-set-77", request.currentPassword)
        assertEquals("My-own-pass-1", request.newPassword)
    }

    @Test
    fun `common mistakes are reported per field`() {
        val short = checkPasswordChange("", "abc", "abd") as PasswordCheck.Invalid
        assertEquals(setOf("current_password", "new_password", "confirm"), short.errors.keys)
        val same = checkPasswordChange("Same-pass-123", "Same-pass-123", "Same-pass-123")
        assertTrue("new_password" in (same as PasswordCheck.Invalid).errors)
    }
}
