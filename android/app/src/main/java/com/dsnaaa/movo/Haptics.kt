package com.dsnaaa.movo

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.HapticFeedbackConstants
import android.view.View

/**
 * 原生触感。跟网页的 navigator.vibrate 比，这里是能控振幅、能用系统预设波形的，
 * 所以能做出"咔哒"而不是"嗡嗡"。小米 15 是 X 轴线性马达，EFFECT_TICK 那一下非常干脆。
 *
 * kind 取值：
 *   tick    滚动落格 / 轻微反馈（最清脆）
 *   click   左键按下
 *   heavy   右键 / 模式切换
 *   soft    轻触（Android 11+ 才有，旧版本回落成 tick）
 *   scroll  连续滚动时的小格（短、弱）
 */
object Haptics {

    private fun vibrator(ctx: Context): Vibrator? = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        }
    } catch (e: Exception) {
        null
    }

    /** 系统调好的 tick，比自己造波形更像真按钮 */
    fun tick(view: View) {
        view.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
    }

    /**
     * 用名字反射取 HapticFeedbackConstants 里的常量 —— 不写死列表，
     * 这样 ROM 新增/删掉某个等级时不用改代码也不会崩。
     */
    fun constId(name: String): Int {
        return try {
            HapticFeedbackConstants::class.java.getField(name).getInt(null)
        } catch (e: Exception) {
            -1
        }
    }

    /**
     * 播放一个命名等级。返回 false 表示这台机器不认这个常量（或 View 未附加到窗口）。
     * force=true 时加 FLAG_IGNORE_GLOBAL_SETTING，绕过系统的「触感反馈」总开关，
     * 用来判断"震不出来"到底是等级不支持还是被设置关掉了。
     */
    fun playConst(view: View, name: String, force: Boolean): Boolean {
        val id = constId(name)
        if (id < 0) return false
        return try {
            if (force && Build.VERSION.SDK_INT >= 33) {
                view.performHapticFeedback(id, HapticFeedbackConstants.FLAG_IGNORE_GLOBAL_SETTING)
            } else {
                view.performHapticFeedback(id)
            }
        } catch (e: Exception) {
            false
        }
    }

    /** 本机 HapticFeedbackConstants 全量清单，给试听页做列表用 */
    fun constList(): String {
        val sb = StringBuilder("[")
        var first = true
        for (f in HapticFeedbackConstants::class.java.fields) {
            if (f.type != Int::class.javaPrimitiveType) continue
            if (f.name.startsWith("FLAG_")) continue
            val v = try {
                f.getInt(null)
            } catch (e: Exception) {
                continue
            }
            if (v < 0) continue
            if (!first) sb.append(',')
            sb.append("{\"name\":\"").append(f.name).append("\",\"value\":").append(v).append('}')
            first = false
        }
        return sb.append(']').toString()
    }

    /** 马达能力，用来解释"为什么某档没感觉" */
    fun info(ctx: Context): String {
        val v = vibrator(ctx) ?: return "{\"hasVibrator\":false}"
        val sb = StringBuilder("{")
        sb.append("\"hasVibrator\":").append(v.hasVibrator())
        sb.append(",\"amplitude\":").append(v.hasAmplitudeControl())
        sb.append(",\"model\":\"").append(Build.MODEL).append('"')
        sb.append(",\"sdk\":").append(Build.VERSION.SDK_INT)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            try {
                // 公开 API 里拿不到 VibratorInfo，只有 areEffectsSupported 这一条路
                val ids = intArrayOf(
                    VibrationEffect.EFFECT_CLICK,
                    VibrationEffect.EFFECT_DOUBLE_CLICK,
                    VibrationEffect.EFFECT_TICK,
                    VibrationEffect.EFFECT_HEAVY_CLICK
                )
                val ok = v.areEffectsSupported(*ids)
                sb.append(",\"effects\":{")
                for (i in ids.indices) {
                    if (i > 0) sb.append(',')
                    sb.append('"').append(ids[i]).append("\":").append(ok[i])
                }
                sb.append('}')
            } catch (e: Exception) {
            }
        }
        return sb.append('}').toString()
    }

    fun play(ctx: Context, kind: String?) {
        val v = vibrator(ctx) ?: return
        if (!v.hasVibrator()) return
        if (!v.hasAmplitudeControl()) {
            // 老机器没有振幅控制，只能给时长
            oneShot(v, if (kind == "scroll") 6L else 12L, 255)
            return
        }
        when (kind) {
            "tick" -> predefined(v, VibrationEffect.EFFECT_TICK)
            "click" -> predefined(v, VibrationEffect.EFFECT_CLICK)
            "heavy" -> predefined(v, VibrationEffect.EFFECT_HEAVY_CLICK)
            "soft" -> oneShot(v, 6L, 110)
            "scroll" -> oneShot(v, 5L, 90)
            else -> oneShot(v, 10L, 160)
        }
    }

    private fun predefined(v: Vibrator, effectId: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                v.vibrate(VibrationEffect.createPredefined(effectId))
                return
            } catch (e: Exception) {
                // 有些 ROM 会拒绝预设波形，退回自造一个短的
            }
        }
        oneShot(v, 10L, 200)
    }

    private fun oneShot(v: Vibrator, ms: Long, amplitude: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            v.vibrate(VibrationEffect.createOneShot(ms, amplitude.coerceIn(1, 255)))
        } else {
            @Suppress("DEPRECATION")
            v.vibrate(ms)
        }
    }
}
