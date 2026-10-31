package com.godaily.driver.core.receipt

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class ReceiptImageTest {
    @Test
    fun `decoder subsampling never goes below the target size`() {
        assertEquals(2, ReceiptImage.sampleSize(4000, 3000)) // 2000 px long side
        assertEquals(1, ReceiptImage.sampleSize(3000, 2000)) // halving would give 1500 < 1600
        assertEquals(4, ReceiptImage.sampleSize(3000, 8000)) // portrait: 2000 px
        assertEquals(1, ReceiptImage.sampleSize(800, 600))
    }

    @Test
    fun `final size keeps the aspect ratio and never upscales`() {
        assertEquals(1600 to 1200, ReceiptImage.targetSize(4000, 3000))
        assertEquals(900 to 1600, ReceiptImage.targetSize(2250, 4000))
        assertEquals(800 to 600, ReceiptImage.targetSize(800, 600))
    }

    @Test
    fun `empty images are refused`() {
        assertThrows<IllegalArgumentException> { ReceiptImage.sampleSize(0, 100) }
        assertThrows<IllegalArgumentException> { ReceiptImage.targetSize(100, 0) }
    }
}
