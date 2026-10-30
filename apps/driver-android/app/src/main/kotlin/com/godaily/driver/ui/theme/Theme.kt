package com.godaily.driver.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection

// Go Daily brand tokens (packages/config/tokens/theme.css).
object Brand {
    val Forest800 = Color(0xFF123B2B)
    val Forest700 = Color(0xFF174A35)
    val Forest50 = Color(0xFFEEF5F1)
    val Lime400 = Color(0xFFA8DF33)
    val Lime100 = Color(0xFFEDFACB)
    val Neutral100 = Color(0xFFF0F2EE)
    val Neutral600 = Color(0xFF585E55)
    val Neutral900 = Color(0xFF1F221E)
    val Danger = Color(0xFFB42318)
    val DangerSoft = Color(0xFFFEE4E2)
    val Warning = Color(0xFF8A5A00)
    val WarningSoft = Color(0xFFFEF0C7)
}

private val colors = lightColorScheme(
    primary = Brand.Forest800,
    onPrimary = Color.White,
    primaryContainer = Brand.Forest50,
    onPrimaryContainer = Brand.Forest800,
    secondary = Brand.Lime400,
    onSecondary = Brand.Forest800,
    background = Brand.Neutral100,
    onBackground = Brand.Neutral900,
    surface = Color.White,
    onSurface = Brand.Neutral900,
    onSurfaceVariant = Brand.Neutral600,
    error = Brand.Danger,
)

/** Arabic UI: always right-to-left, whatever the device language. */
@Composable
fun GoDailyTheme(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        MaterialTheme(colorScheme = colors, content = content)
    }
}
