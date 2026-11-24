package com.godaily.driver.ui.screens

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.R
import com.godaily.driver.core.api.AccountDay
import com.godaily.driver.core.api.CashAccount
import com.godaily.driver.core.cash.egp
import com.godaily.driver.ui.theme.Brand
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val dayFormat: DateTimeFormatter = DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.forLanguageTag("ar"))

private fun isPositive(value: String) = (value.toBigDecimalOrNull() ?: BigDecimal.ZERO).signum() > 0

/** Badge colours by close-out state («في انتظار الإدارة» / جزئي / تم / إجازة). */
private fun badge(kind: String, status: String?): Triple<String, Color, Color> = when {
    kind == "DAY_OFF" -> Triple("إجازة", Brand.NeutralSoft, Brand.Neutral)
    kind == "COLLECTION" -> Triple("تسليم متبقي", Brand.SuccessSoft, Brand.Success)
    status == "WAITING" -> Triple("في انتظار الإدارة", Brand.WarningSoft, Brand.Warning)
    status == "PARTIAL" -> Triple("تحصيل جزئي", Brand.DangerSoft, Brand.Danger)
    status == "COLLECTED" -> Triple("تم التحصيل", Brand.SuccessSoft, Brand.Success)
    else -> Triple("لا يوجد مستحق", Brand.NeutralSoft, Brand.Neutral)
}

/**
 * «حسابي مع الإدارة»: what is still due, what was handed over and the day
 * by day record. The figures come from the close-outs the driver sent and
 * the cash the manager recorded; nothing is estimated on the phone.
 */
@Composable
fun AccountScreen(account: CashAccount?, onBack: () -> Unit, onRefresh: () -> Unit) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().background(Brand.Page)) {
        Box(Modifier.fillMaxWidth().background(Brand.Forest).statusBarsPadding())
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(64.dp)
                .background(Brand.Surface)
                .padding(horizontal = 12.dp),
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                Icon(painterResource(R.drawable.ic_back), contentDescription = "رجوع", tint = Brand.Ink)
            }
            Text(
                "حسابي مع الإدارة",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f).semantics { heading() },
            )
            IconButton(onClick = onRefresh, modifier = Modifier.size(48.dp)) {
                Icon(painterResource(R.drawable.ic_refresh), contentDescription = "تحديث", tint = Brand.Forest)
            }
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(Brand.Line))
        Column(
            verticalArrangement = Arrangement.spacedBy(14.dp),
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(16.dp)
                .navigationBarsPadding(),
        ) {
            if (account == null) {
                Text("تعذر تحميل الحساب الآن. تأكد من الاتصال ثم اضغط تحديث.", fontSize = 14.sp, color = Brand.InkSoft)
            } else {
                Balance(account)
                Text(
                    "الأيام",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 4.dp).semantics { heading() },
                )
                if (account.days.isEmpty()) {
                    Text("لا توجد تقفيلات أو إجازات في هذه الفترة.", fontSize = 14.sp, color = Brand.InkSoft)
                }
                account.days.forEach { DayCard(it) }
            }
        }
    }
}

@Composable
private fun Balance(account: CashAccount) {
    val owed = isPositive(account.outstanding)
    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(Brand.ForestDark)
            .padding(18.dp),
    ) {
        Text(
            if (owed || (account.outstanding.toBigDecimalOrNull()?.signum() ?: 0) == 0) {
                "إجمالي المتبقي عليك (لم يُحصَّل)"
            } else {
                "مستحق لك من الإدارة"
            },
            color = Brand.OnDarkMuted,
            fontSize = 13.sp,
        )
        Text(
            "${egp(account.outstanding.removePrefix("-"))} ج.م",
            color = if (owed) Color(0xFFF6B4B1) else Brand.Lime,
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatTile("للتسليم", egp(account.dueTotal), Modifier.weight(1f), dark = true)
            StatTile("تم تحصيله", egp(account.collectedTotal), Modifier.weight(1f), dark = true)
            StatTile("إجازات", "${account.dayOffDays} يوم", Modifier.weight(1f), dark = true)
        }
        Text(
            "من ${account.dateFrom.format(dayFormat)} · الأرقام يسجّلها المدير بعد استلام النقدية",
            color = Brand.OnDarkMuted,
            fontSize = 11.sp,
        )
    }
}

@Composable
private fun DayCard(day: AccountDay) {
    val closeout = day.closeout
    val dayOff = day.dayOff
    val collection = day.collection
    val (label, soft, tone) = badge(day.kind, closeout?.status)
    GdCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(day.day.format(dayFormat), fontSize = 15.sp, fontWeight = FontWeight.Bold)
                Text(
                    when {
                        closeout != null -> "${closeout.operationLabel} · ${closeout.vehicle.plateNumber}"
                        dayOff != null -> "إجازة مسجّلة ${formatTime(dayOff.createdAt)}"
                        else -> "تسليم مبلغ متبقي من أيام سابقة"
                    },
                    fontSize = 12.sp,
                    color = Brand.InkMuted,
                )
            }
            Pill(label, soft, tone)
        }
        if (closeout != null) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatTile("للتسليم", egp(closeout.totalDue), Modifier.weight(1f))
                StatTile(
                    "تم التحصيل",
                    if (isPositive(closeout.collected)) egp(closeout.collected) else "—",
                    Modifier.weight(1f),
                )
                StatTile(
                    "المتبقي",
                    if (closeout.status == "WAITING") "—" else egp(closeout.remaining),
                    Modifier.weight(1f),
                )
            }
            val last = closeout.collections.lastOrNull()
            Text(
                if (last != null) {
                    "سجّله ${last.collectedBy?.fullName ?: "المدير"} · ${formatTime(last.collectedAt)}"
                } else {
                    "تقفيل مُرسل ${formatTime(closeout.submittedAt)} · لم يُسجَّل التحصيل بعد"
                },
                fontSize = 12.sp,
                color = Brand.InkMuted,
            )
            closeout.collections.mapNotNull { it.note }.lastOrNull()?.let {
                Text(
                    "ملاحظة الإدارة: $it",
                    fontSize = 13.sp,
                    color = Brand.Warning,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(Brand.WarningSoft)
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                )
            }
        }
        dayOff?.note?.let { Text("ملاحظة: $it", fontSize = 13.sp, color = Brand.InkSoft) }
        collection?.let {
            Text(
                "اتسلّم ${egp(it.amount)} ج.م · ${formatTime(it.collectedAt)}",
                fontSize = 13.sp,
                color = Brand.Success,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

/** Short day label for the home card («3 نوفمبر»). */
fun shortDay(day: LocalDate): String = day.format(DateTimeFormatter.ofPattern("d MMMM", Locale.forLanguageTag("ar")))
