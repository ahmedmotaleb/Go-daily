package com.godaily.driver.ui.screens

import androidx.annotation.DrawableRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.ui.theme.Brand

/** White card with the design's 1 px border; [raised] adds the panel shadow. */
@Composable
fun GdCard(
    modifier: Modifier = Modifier,
    raised: Boolean = false,
    padding: Dp = 16.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(20.dp)
    Column(
        modifier = modifier
            .fillMaxWidth()
            .then(if (raised) Modifier.shadow(10.dp, shape, ambientColor = Brand.ForestDark, spotColor = Brand.ForestDark) else Modifier)
            .clip(shape)
            .background(Brand.Surface)
            .border(1.dp, Brand.Line, shape)
            .padding(padding),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        content = content,
    )
}

/** Lime: the one main action on a screen (start shift, confirm). */
@Composable
fun PrimaryButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    height: Dp = 60.dp,
    @DrawableRes icon: Int? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Brand.Lime,
            contentColor = Brand.ForestDark,
            disabledContainerColor = Brand.Disabled,
            disabledContentColor = Brand.InkMuted,
        ),
        modifier = modifier.fillMaxWidth().heightIn(min = height),
    ) { ButtonContent(label, icon, if (height >= 64.dp) 20.sp else 17.sp) }
}

/** Forest: confirming or important secondary actions (end the shift). */
@Composable
fun ForestButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    height: Dp = 56.dp,
    @DrawableRes icon: Int? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(18.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Brand.Forest,
            contentColor = Color.White,
            disabledContainerColor = Brand.Disabled,
            disabledContentColor = Brand.InkMuted,
        ),
        modifier = modifier.fillMaxWidth().heightIn(min = height),
    ) { ButtonContent(label, icon, 17.sp) }
}

/** Outlined secondary action; [critical] uses the red outline for destructive steps. */
@Composable
fun SecondaryButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    critical: Boolean = false,
    height: Dp = 52.dp,
    @DrawableRes icon: Int? = null,
) {
    val tone = if (critical) Brand.Critical else Brand.Forest
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(if (critical) 1.5.dp else 1.dp, if (critical) Brand.Critical else Brand.LineStrong),
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = Brand.Surface,
            contentColor = tone,
            disabledContentColor = Brand.InkMuted,
        ),
        contentPadding = PaddingValues(horizontal = 16.dp),
        modifier = modifier.heightIn(min = height),
    ) { ButtonContent(label, icon, 15.sp) }
}

@Composable
private fun RowScope.ButtonContent(label: String, @DrawableRes icon: Int?, size: androidx.compose.ui.unit.TextUnit) {
    if (icon != null) {
        Icon(painterResource(icon), contentDescription = null, modifier = Modifier.size(22.dp))
        Box(Modifier.size(10.dp))
    }
    Text(label, fontSize = size, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
}

/** Small rounded badge, e.g. «نشطة» or a fuel kind. */
@Composable
fun Pill(text: String, background: Color, content: Color, modifier: Modifier = Modifier) {
    Text(
        text,
        color = content,
        fontSize = 12.sp,
        fontWeight = FontWeight.Bold,
        modifier = modifier
            .clip(CircleShape)
            .background(background)
            .padding(horizontal = 10.dp, vertical = 3.dp),
    )
}

/** Grey tile with a small label over a bold value (stats on cards). */
@Composable
fun StatTile(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    dark: Boolean = false,
    valueSize: androidx.compose.ui.unit.TextUnit = 15.sp,
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(2.dp),
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(if (dark) Color.White.copy(alpha = 0.07f) else Brand.Page)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        Text(label, fontSize = 11.sp, color = if (dark) Brand.OnDarkMuted else Brand.InkMuted)
        Text(value, fontSize = valueSize, fontWeight = FontWeight.Bold, color = if (dark) Color.White else Brand.Ink)
    }
}

/**
 * Egyptian plate as drawn in the design: blue «مصر · EGYPT» strip over the
 * letters and digits. The plate text is shown as recorded; nothing is parsed.
 */
@Composable
fun PlateBadge(plate: String, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(8.dp)
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = modifier
            .widthIn(min = 112.dp)
            .clip(shape)
            .border(2.dp, Brand.Ink, shape)
            .background(Brand.Surface)
            .semantics(mergeDescendants = true) { contentDescription = "رقم اللوحة $plate" },
    ) {
        Text(
            "مصر · EGYPT",
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            color = Brand.ForestDark,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().background(Color(0xFF6FA8DC)).padding(vertical = 1.dp),
        )
        Text(plate, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
    }
}

/** Rounded square holding an icon (state icons, empty states). */
@Composable
fun IconTile(
    @DrawableRes icon: Int,
    background: Color,
    tint: Color,
    size: Dp = 52.dp,
    shape: Shape = RoundedCornerShape(16.dp),
) {
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier.size(size).clip(shape).background(background),
    ) { Icon(painterResource(icon), contentDescription = null, tint = tint, modifier = Modifier.size(size * 0.48f)) }
}

/** Selectable option row: forest 2 px border and soft fill when chosen. */
@Composable
fun ChoiceRow(label: String, selected: Boolean, onClick: () -> Unit, enabled: Boolean = true) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .clip(shape)
            .border(if (selected) 2.dp else 1.dp, if (selected) Brand.Forest else Brand.LineStrong, shape)
            .background(if (selected) Brand.ForestSoft else Brand.Surface)
            .selectable(selected = selected, enabled = enabled, onClick = onClick, role = Role.RadioButton)
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier
                .size(20.dp)
                .clip(CircleShape)
                .border(2.dp, if (selected) Brand.Forest else Brand.LineStrong, CircleShape),
        ) {
            if (selected) Box(Modifier.size(10.dp).clip(CircleShape).background(Brand.Forest))
        }
        Text(
            label,
            fontSize = 15.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            color = if (selected) Brand.Forest else Brand.Ink,
        )
    }
}

@Composable
fun FieldLabel(text: String) {
    Text(text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Brand.Ink)
}

/** Inline message under a form; errors are red text on the soft red tone. */
@Composable
fun FormError(error: String?) {
    if (error == null) return
    Text(
        error,
        color = Brand.Danger,
        fontSize = 13.sp,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(Brand.DangerSoft)
            .padding(horizontal = 12.dp, vertical = 10.dp),
    )
}

/**
 * Bottom sheet used for every driver form (design: start sheet): drag handle,
 * large title, scrollable body, then the main action and a plain cancel.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GdSheet(
    title: String,
    onDismiss: () -> Unit,
    confirm: @Composable () -> Unit,
    dismissLabel: String = "إلغاء",
    content: @Composable ColumnScope.() -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
        containerColor = Brand.Surface,
        contentColor = Brand.Ink,
    ) {
        Column(
            verticalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(start = 20.dp, end = 20.dp, bottom = 24.dp)
                .navigationBarsPadding(),
        ) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            ProvideTextStyle(MaterialTheme.typography.bodyMedium) { content() }
            confirm()
            TextButton(
                onClick = onDismiss,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, Brand.Line),
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
            ) { Text(dismissLabel, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Brand.Ink) }
        }
    }
}
