package com.godaily.driver.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Go Daily design system (packages/config/tokens/theme.css): forest and lime
 * brand, warm neutrals, and status tones whose text colour meets 4.5:1 on its
 * soft background. Lime is for the main action and live tracking only.
 */
object Brand {
    val Forest = Color(0xFF103D32)
    val ForestDark = Color(0xFF082B24)
    val ForestSoft = Color(0xFFEEF4F0)
    val Lime = Color(0xFFB5E33D)
    val LimeText = Color(0xFFD7E8B0)
    val OnDarkMuted = Color(0xFFC9D6D0)

    val Page = Color(0xFFF6F8F5)
    val Surface = Color.White
    val Ink = Color(0xFF202A27)
    val InkSoft = Color(0xFF4F5B56)
    val InkMuted = Color(0xFF5E6B65)
    val Line = Color(0xFFE3EAE5)
    val LineStrong = Color(0xFFD6DFD9)
    val Divider = Color(0xFFEEF2EF)
    val Disabled = Color(0xFFEEF1EF)

    val Success = Color(0xFF3A5A0E)
    val SuccessSoft = Color(0xFFEEF7D9)
    val SuccessDot = Color(0xFF7FA61E)
    val Warning = Color(0xFF7A4E08)
    val WarningSoft = Color(0xFFFDF1DC)
    val WarningDot = Color(0xFFE8A23A)
    val Danger = Color(0xFFA3302C)
    val DangerSoft = Color(0xFFFBE6E5)
    val DangerDot = Color(0xFFD9534F)
    val Info = Color(0xFF24507A)
    val InfoSoft = Color(0xFFE5EEF8)
    val Neutral = Color(0xFF4F5B56)
    val NeutralSoft = Color(0xFFEEF1EF)
    val NeutralDot = Color(0xFF9AA59F)
    val ActiveSoft = Color(0xFFDCE8E2)

    /** Critical actions (end, delete) are outlined in this red, never filled. */
    val Critical = Color(0xFFB83A36)
}

private val colors = lightColorScheme(
    primary = Brand.Forest,
    onPrimary = Color.White,
    primaryContainer = Brand.ForestSoft,
    onPrimaryContainer = Brand.Forest,
    secondary = Brand.Lime,
    onSecondary = Brand.ForestDark,
    background = Brand.Page,
    onBackground = Brand.Ink,
    surface = Brand.Surface,
    onSurface = Brand.Ink,
    surfaceVariant = Brand.Page,
    onSurfaceVariant = Brand.InkSoft,
    outline = Brand.LineStrong,
    outlineVariant = Brand.Line,
    error = Brand.Danger,
    errorContainer = Brand.DangerSoft,
)

// Radii 8/12/16/20/28: fields 12, cards 16-20, sheets 28.
private val shapes = Shapes(
    extraSmall = RoundedCornerShape(12.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

// Sizes follow the driver screens: large, bold numbers; body text at least 13 sp.
private val typography = Typography(
    headlineSmall = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Bold, lineHeight = 30.sp),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.Bold, lineHeight = 28.sp),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.Bold, lineHeight = 24.sp),
    titleSmall = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 22.sp),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 22.sp),
    bodySmall = TextStyle(fontSize = 13.sp, lineHeight = 20.sp),
    labelLarge = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp),
    labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.SemiBold, lineHeight = 16.sp),
    labelSmall = TextStyle(fontSize = 11.sp, lineHeight = 16.sp),
)

/** Arabic UI: always right-to-left, whatever the device language. */
@Composable
fun GoDailyTheme(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        MaterialTheme(colorScheme = colors, shapes = shapes, typography = typography, content = content)
    }
}
