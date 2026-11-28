package com.godaily.driver.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.ui.theme.Brand

/**
 * «غيّر كلمة المرور» (security audit L10): shown instead of the home screen
 * while the office-set password must be changed; nothing can be recorded
 * until then. Passwords are never saved across process death.
 */
@Composable
fun ChangePasswordScreen(
    busy: Boolean,
    error: String?,
    onSubmit: (current: String, new: String, confirm: String) -> Unit,
) {
    var current by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }

    Column(
        verticalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier
            .fillMaxSize()
            .background(Brand.Page)
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(16.dp),
    ) {
        GdCard(raised = true, padding = 20.dp) {
            Text(
                "غيّر كلمة المرور",
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.semantics { heading() },
            )
            Text(
                "الإدارة أعطتك كلمة المرور الحالية. اختر كلمة مرور خاصة بك قبل تسجيل أي بيانات.",
                fontSize = 14.sp,
                color = Brand.InkSoft,
            )
            PasswordField("كلمة المرور الحالية", current) { current = it }
            PasswordField("كلمة المرور الجديدة", new) { new = it }
            PasswordField("تأكيد كلمة المرور الجديدة", confirm) { confirm = it }
            if (error != null) {
                Column(Modifier.semantics { liveRegion = LiveRegionMode.Polite }) { FormError(error) }
            }
            if (busy) {
                Column(
                    modifier = Modifier.fillMaxWidth().heightIn(min = 60.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) { CircularProgressIndicator(color = Brand.Forest, strokeWidth = 3.dp, modifier = Modifier.size(32.dp)) }
            } else {
                PrimaryButton("حفظ كلمة المرور", { onSubmit(current, new, confirm) })
            }
        }
    }
}

@Composable
private fun PasswordField(label: String, value: String, onChange: (String) -> Unit) {
    FieldLabel(label)
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        singleLine = true,
        textStyle = TextStyle(fontSize = 18.sp),
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
    )
}
