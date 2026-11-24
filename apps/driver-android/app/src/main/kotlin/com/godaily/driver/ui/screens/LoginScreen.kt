package com.godaily.driver.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.R
import com.godaily.driver.ui.theme.Brand

@Composable
fun LoginScreen(busy: Boolean, error: String?, onLogin: (phone: String, password: String) -> Unit) {
    var phone by rememberSaveable { mutableStateOf("") }
    // Not saved across process death on purpose.
    var password by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Brand.Page)
            .verticalScroll(rememberScrollState())
            .imePadding(),
    ) {
        Column(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(bottomStart = 28.dp, bottomEnd = 28.dp))
                .background(Brand.Forest)
                .statusBarsPadding()
                .padding(start = 24.dp, end = 24.dp, top = 40.dp, bottom = 72.dp),
        ) {
            Image(
                painterResource(R.drawable.logo_on_dark),
                contentDescription = "GO DAILY",
                contentScale = ContentScale.FillWidth,
                modifier = Modifier.width(150.dp),
            )
            Text(
                "تطبيق السائق",
                color = Brand.OnDarkMuted,
                fontSize = 15.sp,
                modifier = Modifier.semantics { heading() },
            )
        }
        Column(
            modifier = Modifier
                .offset(y = (-44).dp)
                .padding(horizontal = 16.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            GdCard(raised = true, padding = 20.dp) {
                Text("تسجيل الدخول", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                FieldLabel("رقم الهاتف")
                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    placeholder = { Text("01xxxxxxxxx") },
                    singleLine = true,
                    textStyle = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.SemiBold),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone, imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                )
                FieldLabel("كلمة المرور")
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    singleLine = true,
                    textStyle = TextStyle(fontSize = 18.sp),
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                )
                if (error != null) {
                    Column(Modifier.semantics { liveRegion = LiveRegionMode.Polite }) { FormError(error) }
                }
                if (busy) {
                    Column(
                        modifier = Modifier.fillMaxWidth().heightIn(min = 60.dp),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
                    ) { CircularProgressIndicator(color = Brand.Forest, strokeWidth = 3.dp, modifier = Modifier.size(32.dp)) }
                } else {
                    PrimaryButton("تسجيل الدخول", { onLogin(phone, password) })
                }
            }
            Text(
                "للسائقين المسجلين فقط. تواصل مع إدارة التشغيل إذا نسيت كلمة المرور.",
                fontSize = 13.sp,
                color = Brand.InkSoft,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}
