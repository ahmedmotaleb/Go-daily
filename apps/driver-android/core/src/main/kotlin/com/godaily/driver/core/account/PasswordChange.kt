package com.godaily.driver.core.account

import com.godaily.driver.core.api.ChangePasswordRequest

/**
 * «غيّر كلمة المرور» (security audit L10): when the office set the password,
 * the driver replaces it before recording anything. The server applies its
 * own policy too; these checks catch the common mistakes before sending.
 */
sealed interface PasswordCheck {
    data class Valid(val request: ChangePasswordRequest) : PasswordCheck

    /** Field (API name, or "confirm") → Arabic message. */
    data class Invalid(val errors: Map<String, String>) : PasswordCheck
}

const val PASSWORD_MIN_LENGTH = 8

fun checkPasswordChange(current: String, new: String, confirm: String): PasswordCheck {
    val errors = linkedMapOf<String, String>()
    if (current.isEmpty()) errors["current_password"] = "أدخل كلمة المرور الحالية"
    when {
        new.length < PASSWORD_MIN_LENGTH ->
            errors["new_password"] = "كلمة المرور الجديدة لا تقل عن $PASSWORD_MIN_LENGTH أحرف"
        new.trim() != new -> errors["new_password"] = "بدون مسافات في البداية أو النهاية"
        new == current -> errors["new_password"] = "اختر كلمة مرور مختلفة عن الحالية"
    }
    if (confirm != new) errors["confirm"] = "تأكيد كلمة المرور غير مطابق"
    return if (errors.isEmpty()) {
        PasswordCheck.Valid(ChangePasswordRequest(currentPassword = current, newPassword = new))
    } else {
        PasswordCheck.Invalid(errors)
    }
}
