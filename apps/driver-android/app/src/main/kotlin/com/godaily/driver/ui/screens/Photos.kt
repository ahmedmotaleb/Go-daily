package com.godaily.driver.ui.screens

import android.content.ActivityNotFoundException
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.godaily.driver.R
import com.godaily.driver.receipt.ReceiptPhotos
import com.godaily.driver.ui.theme.Brand
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Small preview of a photo the driver just took (decoded off the main thread). */
@Composable
private fun rememberThumbnail(uri: Uri?): ImageBitmap? {
    val context = LocalContext.current
    val thumbnail by produceState<ImageBitmap?>(initialValue = null, uri) {
        value = if (uri == null) {
            null
        } else {
            withContext(Dispatchers.IO) {
                runCatching {
                    val options = BitmapFactory.Options().apply { inSampleSize = 8 }
                    context.contentResolver.openInputStream(uri)
                        ?.use { BitmapFactory.decodeStream(it, null, options) }
                        ?.asImageBitmap()
                }.getOrNull()
            }
        }
    }
    return thumbnail
}

/**
 * Camera capture for a photo the flow needs (design: «صوّر العداد»): a large
 * dashed button, then a preview with «إعادة التصوير». The photo is kept in
 * the app's private cache and prepared (resized, EXIF removed) on upload.
 */
@Composable
fun PhotoCapture(
    photo: Uri?,
    onPhoto: (Uri?) -> Unit,
    takeLabel: String,
    hint: String,
    takenLabel: String,
    onCameraMissing: () -> Unit,
    compact: Boolean = false,
) {
    val context = LocalContext.current
    // Saveable: the activity can be recreated while the camera app is open.
    var pending by rememberSaveable { mutableStateOf<Uri?>(null) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        if (saved) onPhoto(pending)
    }
    val launch = {
        val target = ReceiptPhotos.newCaptureUri(context)
        pending = target
        try {
            camera.launch(target)
        } catch (_: ActivityNotFoundException) {
            onCameraMissing()
        }
    }
    if (photo == null) {
        val shape = RoundedCornerShape(16.dp)
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterVertically),
            modifier = Modifier
                .fillMaxWidth()
                .height(if (compact) 72.dp else 132.dp)
                .clip(shape)
                .background(Brand.Page)
                .drawBehind {
                    drawRoundRect(
                        color = Brand.Forest,
                        style = Stroke(
                            width = 2.dp.toPx(),
                            pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f)),
                        ),
                        cornerRadius = CornerRadius(16.dp.toPx()),
                    )
                }
                .clickable(role = Role.Button, onClick = launch),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(
                    painterResource(R.drawable.ic_camera),
                    contentDescription = null,
                    tint = Brand.Forest,
                    modifier = Modifier.size(if (compact) 22.dp else 28.dp),
                )
                Text(takeLabel, color = Brand.Forest, fontSize = 15.sp, fontWeight = FontWeight.Bold)
            }
            if (!compact) Text(hint, color = Brand.InkSoft, fontSize = 12.sp)
        }
        return
    }
    val thumbnail = rememberThumbnail(photo)
    val shape = RoundedCornerShape(16.dp)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Color(0xFFF4FAE6))
            .border(1.dp, Color(0xFFCFE3A8), shape)
            .padding(10.dp),
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier
                .size(width = 120.dp, height = 84.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(Color(0xFF1B2320)),
        ) {
            if (thumbnail != null) {
                Image(
                    bitmap = thumbnail,
                    contentDescription = takenLabel,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(84.dp),
                )
            }
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(takenLabel, color = Brand.Success, fontSize = 14.sp, fontWeight = FontWeight.Bold)
            SecondaryButton("إعادة التصوير", { launch() }, height = 40.dp)
        }
    }
}
