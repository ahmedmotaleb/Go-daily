package com.godaily.driver.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.godaily.driver.container

private enum class Step { DISCLOSURE, LOCATION, NOTIFICATIONS, BACKGROUND, BATTERY, DONE }

private fun satisfied(context: Context, step: Step): Boolean {
    val c = context.container
    return when (step) {
        Step.DISCLOSURE -> c.shiftState.disclosureAccepted
        Step.LOCATION -> c.device.hasFineLocation()
        Step.NOTIFICATIONS -> Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU || c.device.notificationsAllowed()
        Step.BACKGROUND -> c.device.hasBackgroundLocation()
        Step.BATTERY -> c.device.batteryOptimizationExempt()
        Step.DONE -> true
    }
}

/** First unsatisfied step after [after] (optional steps can be skipped). */
private fun nextStep(context: Context, after: Step? = null): Step =
    Step.entries.dropWhile { after != null && it.ordinal <= after.ordinal }
        .firstOrNull { !satisfied(context, it) } ?: Step.DONE

/**
 * Prominent disclosure and permission onboarding. The disclosure is shown
 * before any location permission request, as Google Play requires for
 * location used while the app is not in use.
 */
@Composable
fun PermissionScreen(onAcceptDisclosure: () -> Unit, onFinished: () -> Unit, onCancel: () -> Unit) {
    val context = LocalContext.current
    var step by remember { mutableStateOf(nextStep(context)) }
    var denied by remember { mutableStateOf(false) }

    fun advance(from: Step) {
        step = nextStep(context, from)
    }

    LaunchedEffect(step) {
        if (step == Step.DONE) onFinished()
    }

    val location = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if (context.container.device.hasFineLocation()) advance(Step.LOCATION) else denied = true
    }
    val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        advance(Step.NOTIFICATIONS)
    }
    val background = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        advance(Step.BACKGROUND)
    }

    if (step == Step.DONE) return

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            when (step) {
                Step.DISCLOSURE -> {
                    Title("تتبع موقع المركبة أثناء الوردية")
                    Body(
                        "يجمع تطبيق Go Daily موقع المركبة (الإحداثيات والسرعة والدقة والوقت) أثناء ورديات العمل " +
                            "فقط، حتى عندما يكون التطبيق مغلقًا أو الشاشة مقفلة.",
                    )
                    Body(
                        "الغرض: عرض موقع المركبة لإدارة التشغيل، وحساب المسافة وعدد الدورات، ومتابعة " +
                            "الالتزام بالخطوط. لا يُستخدم الموقع لأي غرض آخر.",
                    )
                    Body(
                        "يبدأ التتبع عند بدء الوردية ويتوقف تلقائيًا عند إنهائها، ويظهر إشعار دائم طوال مدة " +
                            "التتبع. لا يتم جمع الموقع خارج الوردية.",
                    )
                    Primary("موافق ومتابعة") {
                        onAcceptDisclosure()
                        advance(Step.DISCLOSURE)
                    }
                    TextButton(onClick = onCancel) { Text("ليس الآن") }
                }
                Step.LOCATION -> {
                    Title("إذن الموقع")
                    Body("اختر «أثناء استخدام التطبيق» مع «الموقع الدقيق». بدون هذا الإذن لا يمكن بدء الوردية.")
                    if (denied) {
                        Text(
                            "تم رفض الإذن. إذا لم تظهر نافذة الطلب، افتح إعدادات التطبيق وفعّل الموقع.",
                            color = MaterialTheme.colorScheme.error,
                        )
                        TextButton(onClick = { openAppSettings(context) }) { Text("فتح إعدادات التطبيق") }
                    }
                    Primary("منح إذن الموقع") {
                        location.launch(
                            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                        )
                    }
                    TextButton(onClick = onCancel) { Text("رجوع") }
                }
                Step.NOTIFICATIONS -> {
                    Title("الإشعارات")
                    Body("يظهر إشعار دائم أثناء التتبع ليعرف السائق أن الموقع يُسجَّل، وتنبيه إذا توقف التتبع.")
                    Primary("السماح بالإشعارات") {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            advance(Step.NOTIFICATIONS)
                        }
                    }
                    TextButton(onClick = { advance(Step.NOTIFICATIONS) }) { Text("تخطي") }
                }
                Step.BACKGROUND -> {
                    Title("السماح طوال الوقت (مُستحسن)")
                    Body(
                        "اختر «السماح طوال الوقت» حتى يستأنف التتبع تلقائيًا إذا أُعيد تشغيل الهاتف أثناء الوردية. " +
                            "بدونه ستحتاج لفتح التطبيق بعد إعادة التشغيل. لا يُجمع الموقع خارج الوردية في الحالتين.",
                    )
                    Primary("فتح خيار «السماح طوال الوقت»") {
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                            background.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
                        } else {
                            advance(Step.BACKGROUND)
                        }
                    }
                    TextButton(onClick = { advance(Step.BACKGROUND) }) { Text("تخطي") }
                }
                Step.BATTERY -> {
                    Title("تحسين البطارية")
                    Body(
                        "بعض الهواتف توقف التطبيقات في الخلفية لتوفير البطارية، فيتوقف التتبع أثناء الوردية. " +
                            "استثنِ Go Daily من تحسين البطارية من الإعدادات.",
                    )
                    Primary("فتح إعدادات البطارية") {
                        context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    }
                    TextButton(onClick = { advance(Step.BATTERY) }) { Text("متابعة") }
                }
                Step.DONE -> Unit
            }
        }
    }
}

@Composable
private fun Title(text: String) =
    Text(text, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)

@Composable
private fun Body(text: String) = Text(text, style = MaterialTheme.typography.bodyLarge)

@Composable
private fun Primary(label: String, onClick: () -> Unit) {
    Button(onClick = onClick, modifier = Modifier.fillMaxWidth().height(52.dp)) { Text(label) }
}
