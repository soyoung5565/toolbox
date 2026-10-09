package com.ai.teleprompter

import android.app.Application
import android.util.Log
import com.ai.teleprompter.asr.AsrEngine
import com.ai.teleprompter.audio.AudioCapture
import com.ai.teleprompter.align.ScriptAligner
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * 全局状态：稿件、当前 cursor、是否在录音、模型是否加载完、ASR 文本。
 */
class TeleprompterState(app: Application) {
    private val appCtx = app.applicationContext

    val asrEngine: AsrEngine = AsrEngine(appCtx)
    // 每 2s 累积音频送入 OfflineRecognizer
    val audioCapture: AudioCapture = AudioCapture(appCtx) { pcm ->
        try {
            val text = asrEngine.recognizeSegment(pcm)
            if (!text.isNullOrBlank()) {
                onRecognizedSegment(text)
            }
        } catch (e: Throwable) {
            Log.w("TeleprompterState", "recognize 出错: ${e.message}")
        }
    }

    @Volatile private var aligner: ScriptAligner? = null

    private val _scriptText = MutableStateFlow("")
    val scriptText: StateFlow<String> = _scriptText

    private val _currentIndex = MutableStateFlow(-1)
    val currentIndex: StateFlow<Int> = _currentIndex

    private val _isRunning = MutableStateFlow(false)
    val isRunning: StateFlow<Boolean> = _isRunning

    private val _modelLoaded = MutableStateFlow(false)
    val modelLoaded: StateFlow<Boolean> = _modelLoaded

    private val _asrText = MutableStateFlow("")
    val asrText: StateFlow<String> = _asrText

    private val _status = MutableStateFlow("未开始")
    val status: StateFlow<String> = _status

    fun setScript(text: String) {
        _scriptText.value = text
        aligner = if (text.isBlank()) null else ScriptAligner(text)
        _currentIndex.value = -1
    }

    fun toggleRecording() {
        if (_isRunning.value) stopRecording() else startRecording()
    }

    fun startRecording() {
        if (_isRunning.value) return
        if (aligner == null) {
            _status.value = "请先粘贴稿件"
            return
        }
        if (!_modelLoaded.value) {
            _status.value = "模型加载中…"
            try {
                asrEngine.load()
                _modelLoaded.value = true
            } catch (e: Throwable) {
                Log.e(TAG, "模型加载失败", e)
                _status.value = "模型加载失败: ${e.message}"
                return
            }
        }
        asrEngine.reset()
        aligner?.reset()
        _currentIndex.value = -1
        _asrText.value = ""
        audioCapture.start()
        _isRunning.value = true
        _status.value = "识别中（每 2s）…"
    }

    fun stopRecording() {
        if (!_isRunning.value) return
        audioCapture.stop()
        _isRunning.value = false
        _status.value = "已停止"
    }

    /** 每 2 秒识别一次后调用此方法：把识别结果喂给 aligner */
    private fun onRecognizedSegment(text: String) {
        val aligner = aligner ?: return
        _asrText.value = text
        val newIdx = aligner.update(text, isFinal = true)
        _currentIndex.value = newIdx
    }

    /** 占位：UI tick 接口（离线版不需要） */
    fun pollAsrTick() { /* no-op */ }

    fun dispose() {
        stopRecording()
        asrEngine.release()
    }

    companion object {
        private const val TAG = "TeleprompterState"
    }
}