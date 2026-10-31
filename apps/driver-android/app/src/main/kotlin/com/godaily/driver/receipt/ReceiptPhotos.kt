package com.godaily.driver.receipt

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import androidx.core.content.FileProvider
import com.godaily.driver.core.receipt.ReceiptImage
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Receipt photos: a private cache file for the camera to write into, and
 * preparation before upload (decode at reduced size, apply the camera's
 * rotation, re-encode as JPEG). Re-encoding also drops the photo's EXIF
 * metadata, including any location the camera app embedded.
 */
object ReceiptPhotos {
    private const val DIR = "receipts"

    fun newCaptureUri(context: Context): Uri {
        val dir = File(context.cacheDir, DIR).apply { mkdirs() }
        val file = File(dir, "receipt-${System.currentTimeMillis()}.jpg")
        return FileProvider.getUriForFile(context, "${context.packageName}.receipts", file)
    }

    suspend fun prepare(context: Context, uri: Uri): ByteArray = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            ?: throw IOException("تعذر فتح الصورة")
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw IOException("الملف المختار ليس صورة")

        val options = BitmapFactory.Options().apply {
            inSampleSize = ReceiptImage.sampleSize(bounds.outWidth, bounds.outHeight)
        }
        val decoded = resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) }
            ?: throw IOException("تعذر قراءة الصورة")
        val rotation = resolver.openInputStream(uri)?.use { rotationDegrees(ExifInterface(it)) } ?: 0

        val (width, height) = ReceiptImage.targetSize(decoded.width, decoded.height)
        val matrix = Matrix().apply {
            postScale(width.toFloat() / decoded.width, height.toFloat() / decoded.height)
            if (rotation != 0) postRotate(rotation.toFloat())
        }
        val prepared = Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
        try {
            ByteArrayOutputStream().use { out ->
                prepared.compress(Bitmap.CompressFormat.JPEG, ReceiptImage.JPEG_QUALITY, out)
                out.toByteArray()
            }
        } finally {
            if (prepared !== decoded) prepared.recycle()
            decoded.recycle()
        }
    }

    /** Removes photos taken for receipts once they are uploaded or abandoned. */
    fun clearCache(context: Context) {
        File(context.cacheDir, DIR).listFiles()?.forEach { it.delete() }
    }

    private fun rotationDegrees(exif: ExifInterface): Int =
        when (exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90
            ExifInterface.ORIENTATION_ROTATE_180 -> 180
            ExifInterface.ORIENTATION_ROTATE_270 -> 270
            else -> 0
        }
}
