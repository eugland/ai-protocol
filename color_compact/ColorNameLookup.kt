package com.primortex.color.service

import kotlin.math.*

/**
 * Uses pre-binned LAB index generated into ColorIndex.kt (or any object with the same fields)
 *
 * Expected fields in ColorIndex object:
 *  - names: Array<String>
 *  - L, A, B: FloatArray (CIELAB per entry)
 *  - bucketKey, bucketStart, bucketLen, bucketItems: IntArray
 *  - L_STEP, A_STEP, B_STEP: Float
 */
object ColorNameLookup {

    data class Lab(val l: Float, val a: Float, val b: Float)
    data class Result(
        val name: String,
        val deltaE: Float,
        val index: Int
    )

    /** Convert ARGB int (0xAARRGGBB) to CIE LAB (D65) */
    fun argbToLab(argb: Int): Lab {
        val r = ((argb ushr 16) and 0xFF) / 255f
        val g = ((argb ushr 8) and 0xFF) / 255f
        val b = (argb and 0xFF) / 255f

        fun pivot(u: Float): Float =
            if (u > 0.04045f) (((u + 0.055f) / 1.055f).toDouble().pow(2.4)).toFloat() else (u / 12.92f)

        val rr = pivot(r)
        val gg = pivot(g)
        val bb = pivot(b)

        // linear RGB -> XYZ (D65)
        val x = (0.4124f * rr + 0.3576f * gg + 0.1805f * bb) / 0.95047f
        val y = (0.2126f * rr + 0.7152f * gg + 0.0722f * bb)
        val z = (0.0193f * rr + 0.1192f * gg + 0.9505f * bb) / 1.08883f

        fun f(t: Float): Float =
            if (t > 0.008856f) cbrt(t) else (7.787f * t + 16f / 116f)

        val fx = f(x)
        val fy = f(y)
        val fz = f(z)

        val L = 116f * fy - 16f
        val A = 500f * (fx - fy)
        val B = 200f * (fy - fz)
        return Lab(L, A, B)
    }

    /** A fast perceptual distance. (ΔE76) */
    private fun deltaE76(p: Lab, i: Int): Float {
        val dl = p.l - ColorIndex.L[i]
        val da = p.a - ColorIndex.A[i]
        val db = p.b - ColorIndex.B[i]
        return sqrt(dl * dl + da * da + db * db)
    }

    private fun clamp(v: Int, lo: Int, hi: Int) = when {
        v < lo -> lo
        v > hi -> hi
        else -> v
    }

    private fun findBucketKey(key: Int): Int {
        val keys = ColorIndex.bucketKey
        var lo = 0
        var hi = keys.size - 1
        while (lo <= hi) {
            val mid = (lo + hi) ushr 1
            val v = keys[mid]
            when {
                v < key -> lo = mid + 1
                v > key -> hi = mid - 1
                else -> return mid
            }
        }
        return -1
    }

    /**
     * Lookup nearest name for a given ARGB (0xAARRGGBB).
     *
     * maxRadius:
     *  - 0 = only same bin (fastest, may miss if that bin is empty)
     *  - 1..3 = expands to neighbor bins (recommended 2)
     */
    fun nearestName(argb: Int, maxRadius: Int = 2): Result {
        val q = argbToLab(argb)

        // Base bins
        val lMax = (100f / ColorIndex.L_STEP).toInt()
        val aMax = (256f / ColorIndex.A_STEP).toInt() - 1
        val bMax = (256f / ColorIndex.B_STEP).toInt() - 1

        val l0 = clamp((q.l / ColorIndex.L_STEP).toInt(), 0, lMax)
        val a0 = clamp(((q.a + 128f) / ColorIndex.A_STEP).toInt(), 0, aMax)
        val b0 = clamp(((q.b + 128f) / ColorIndex.B_STEP).toInt(), 0, bMax)

        var bestIdx = 0
        var bestD = Float.MAX_VALUE

        fun evalCandidate(colorIdx: Int) {
            val d = deltaE76(q, colorIdx)
            if (d < bestD) {
                bestD = d
                bestIdx = colorIdx
            }
        }

        // Expand search cube by radius until we find candidates
        for (r in 0..maxRadius) {
            var foundAny = false

            for (dl in -r..r) for (da in -r..r) for (db in -r..r) {
                val lb = l0 + dl
                val ab = a0 + da
                val bb = b0 + db
                if (lb !in 0..lMax || ab !in 0..aMax || bb !in 0..bMax) continue

                val key = (lb shl 12) or (ab shl 6) or bb
                val bi = findBucketKey(key)
                if (bi < 0) continue

                val start = ColorIndex.bucketStart[bi]
                val len = ColorIndex.bucketLen[bi]
                for (k in 0 until len) {
                    evalCandidate(ColorIndex.bucketItems[start + k])
                }

                foundAny = true
            }

            if (foundAny) break
        }

        return Result(
            name = ColorIndex.names[bestIdx],
            deltaE = bestD,
            index = bestIdx
        )
    }

    /** Helper: displays as "≈ Name" if distance is high. Tune threshold to taste. */
    fun prettyLabel(result: Result, approxThreshold: Float = 10f): String {
        return if (result.deltaE <= approxThreshold) result.name else "≈ ${result.name}"
    }

    /** cbrt for Float */
    private fun cbrt(x: Float): Float = Math.cbrt(x.toDouble()).toFloat()
}


fun main() {
    val argb = 0xFF0048BA.toInt() // Absolute Zero-ish
    val res = ColorNameLookup.nearestName(argb)
    val label = ColorNameLookup.prettyLabel(res)

    println("Name=${res.name}, label=$label, deltaE=${res.deltaE}")
}