package com.ai.teleprompter.asr

import android.content.Context
import android.content.res.AssetManager
import android.util.Log
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.HomophoneReplacerConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineParaformerModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineStream
import java.io.File
import java.io.FileOutputStream

/**
 * sherpa-onnx **Paraformer 离线** 识别器。
 *
 * 使用 sherpa-onnx-paraformer-zh-2024-03-09（中文专用离线模型）：
 * - 单个 ONNX 模型（非 transducer 三件套）
 * - 中文识别准确率高
 * - 离线 + 完全本地
 *
 * 工作方式：每收到 2 秒 PCM 就用 OfflineRecognizer 识别一次（准流式）。
 */
class AsrEngine(
    private val context: Context,
) {
    @Volatile private var recognizer: OfflineRecognizer? = null

    val sampleRate: Int = 16000

    /** 加载模型（同步） */
    fun load() {
        if (recognizer != null) return
        val modelDirName = MODEL_DIR_NAME
        val cfg = buildConfig(modelDirName)
        val dstRoot = File(context.filesDir, modelDirName)
        if (!dstRoot.exists() || dstRoot.list().isNullOrEmpty()) {
            copyAssetDir(context.assets, modelDirName, dstRoot)
            Log.i(TAG, "模型已拷到 ${dstRoot.absolutePath}")
        }
        val finalCfg = cfg.withAbsolutePaths(dstRoot.absolutePath)
        recognizer = OfflineRecognizer(null, finalCfg)
    }

    /**
     * 把一段累积的 PCM 16kHz mono Float [-1, 1] 喂给识别器。
     * 返回识别出的文本。
     */
    fun recognizeSegment(samples: FloatArray): String? {
        val r = recognizer ?: return null
        if (samples.size < sampleRate / 4) return null
        val s = r.createStream()
        return try {
            s.acceptWaveform(samples, sampleRate)
            r.decode(s)
            val result = r.getResult(s)
            s.release()
            result.text
        } catch (e: Throwable) {
            Log.w(TAG, "recognizeSegment 失败: ${e.message}")
            try { s.release() } catch (_: Throwable) {}
            null
        }
    }

    fun reset() { /* no-op */ }

    fun release() {
        recognizer?.release()
        recognizer = null
    }

    private fun buildConfig(modelDirName: String): OfflineRecognizerConfig {
        // Paraformer 单模型
        val model = OfflineModelConfig(
            paraformer = OfflineParaformerModelConfig(
                model = "$modelDirName/model.int8.onnx",
            ),
            tokens = "$modelDirName/tokens.txt",
            modelType = "paraformer",
        )
        return OfflineRecognizerConfig(
            featConfig = FeatureConfig(),  // 默认值
            modelConfig = model,
            hr = HomophoneReplacerConfig(),
            decodingMethod = "greedy_search",
        )
    }

    private fun OfflineRecognizerConfig.withAbsolutePaths(root: String): OfflineRecognizerConfig {
        val r = root.replace("\\", "/")
        val mc = modelConfig
        return copy(
            modelConfig = mc.copy(
                paraformer = mc.paraformer.copy(
                    model = mc.paraformer.model.toAbsolute(r),
                ),
                tokens = mc.tokens.toAbsolute(r),
            )
        )
    }

    private fun String.toAbsolute(root: String): String =
        if (isBlank() || startsWith("/") || contains(":\\") || contains(":/")) this
        else "$root/${substringAfter('/')}"

    private fun copyAssetDir(am: AssetManager, assetPath: String, dst: File) {
        dst.mkdirs()
        val files = am.list(assetPath) ?: return
        for (f in files) {
            val sub = if (assetPath.isEmpty()) f else "$assetPath/$f"
            val subDst = File(dst, f)
            val nested = am.list(sub)
            if (nested != null && nested.isNotEmpty()) {
                copyAssetDir(am, sub, subDst)
            } else {
                copyAssetFile(am, sub, subDst)
            }
        }
    }

    private fun copyAssetFile(am: AssetManager, assetPath: String, dst: File) {
        if (dst.exists() && dst.length() > 0) return
        dst.parentFile?.mkdirs()
        am.open(assetPath).use { input ->
            FileOutputStream(dst).use { output ->
                input.copyTo(output)
            }
        }
    }

    companion object {
        private const val TAG = "AsrEngine"
        const val MODEL_DIR_NAME = "sherpa-onnx-paraformer-zh-2024-03-09"
    }
}