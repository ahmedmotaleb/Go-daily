package com.godaily.driver.core.receipt

import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Sizing for receipt photos before upload. Phone cameras produce 10+ MB
 * images; the server accepts up to 10 MB and a receipt stays readable at
 * about 1600 px on its long side, so photos are shrunk before sending.
 */
object ReceiptImage {
    const val MAX_SIDE_PX = 1600
    const val JPEG_QUALITY = 80

    /**
     * Largest power-of-two decoder subsampling that keeps the long side at
     * or above [maxSide] (Android's `inSampleSize`), so decoding never loads
     * the full-resolution bitmap and never goes below the target size.
     */
    fun sampleSize(width: Int, height: Int, maxSide: Int = MAX_SIDE_PX): Int {
        require(width > 0 && height > 0) { "empty image" }
        var size = 1
        val longSide = max(width, height)
        while (longSide / (size * 2) >= maxSide) size *= 2
        return size
    }

    /** Final dimensions: long side at most [maxSide], aspect ratio kept, never upscaled. */
    fun targetSize(width: Int, height: Int, maxSide: Int = MAX_SIDE_PX): Pair<Int, Int> {
        require(width > 0 && height > 0) { "empty image" }
        val longSide = max(width, height)
        if (longSide <= maxSide) return width to height
        val scale = maxSide.toDouble() / longSide
        return max(1, (width * scale).roundToInt()) to max(1, (height * scale).roundToInt())
    }
}
