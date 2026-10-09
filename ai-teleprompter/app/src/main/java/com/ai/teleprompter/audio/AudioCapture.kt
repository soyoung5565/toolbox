package com.ai.teleprompter.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlin.concurrent.thread

/**
 * 16kHz mono PCM 音频采集 —— 累积 2 秒后批量回调。
 *
 * sherpa-onnx OfflineRecognizer 要求整段 Float PCM 输入。
 * 每 2 秒（16000 * 2 = 32000 samples）触发一次 onSegment 回调，
 * 上层把这段音频送去识别。
 */
class AudioCapture(
    private val context: Context,
    private val sampleRate: Int = 16000,
    /** 回调：每 ~2s 拿到一段 Float PCM（约 32000 samples） */
    private val onSegment: (FloatArray) -> Unit,
) {
    private var audioRecord: AudioRecord? = null
    @Volatile private var running: Boolean = false
    private var captureThread: Thread? = null

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    fun start() {
        if (running) return
        if (!hasPermission()) {
            Log.w(TAG, "没有录音权限")
            return
        }
        val channelConfig = AudioFormat.CHANNEL_IN_MONO
        val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        val minBuf = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
        if (minBuf <= 0) {
            Log.e(TAG, "getMinBufferSize 失败: $minBuf")
            return
        }
        val bufSize = maxOf(minBuf, sampleRate * 2)

        val record = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            channelConfig,
            audioFormat,
            bufSize,
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord 初始化失败")
            record.release()
            return
        }
        audioRecord = record
        running = true
        record.startRecording()

        captureThread = thread(name = "audio-capture") {
            val shortBuf = ShortArray(bufSize / 2)
            val segmentSamples = SEGMENT_SAMPLES
            val fullBuf = FloatArray(segmentSamples)
            var filled = 0
            while (running) {
                val n = record.read(shortBuf, 0, shortBuf.size)
                if (n <= 0) continue
                var i = 0
                while (i < n) {
                    val take = minOf(segmentSamples - filled, n - i)
                    for (j in 0 until take) {
                        fullBuf[filled + j] = shortBuf[i + j] / 32768.0f
                    }
                    filled += take
                    i += take
                    if (filled >= segmentSamples) {
                        onSegment(fullBuf.copyOf(filled))
                        filled = 0
                    }
                }
            }
        }
    }

    fun stop() {
        running = false
        captureThread?.join(500)
        captureThread = null
        audioRecord?.let {
            try { it.stop() } catch (_: Throwable) {}
            it.release()
        }
        audioRecord = null
    }

    companion object {
        private const val TAG = "AudioCapture"
        // 0.5 秒一段 PCM（8000 samples @ 16kHz），匹配 paraformer 默认输入尺寸
        private const val SEGMENT_SAMPLES = 16000 * 500 / 1000
    }
}