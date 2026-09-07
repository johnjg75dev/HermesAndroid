package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result
import kotlinx.coroutines.CompletableDeferred
import java.util.Locale

class TtsFacadeImpl(private val context: Context) : DeviceFacade {

    private var tts: TextToSpeech? = null
    private var initDeferred: CompletableDeferred<Unit>? = null

    init {
        initTts()
    }

    private fun initTts() {
        initDeferred = CompletableDeferred()
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                initDeferred?.complete(Unit)
            } else {
                initDeferred?.completeExceptionally(Exception("TTS init failed"))
            }
        }
    }

    override suspend fun ttsSpeak(
        text: String,
        language: String?,
        runId: String?,
    ): Result<Unit> {
        return try {
            initDeferred?.await()
            tts ?: return Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "TTS not initialized"))

            val locale = language?.let { Locale.forLanguageTag(it) } ?: Locale.getDefault()
            val result = tts!!.setLanguage(locale)
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                return Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Language not supported: $language"))
            }

            val deferred = CompletableDeferred<Unit>()
            tts!!.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) {
                    deferred.complete(Unit)
                }
                override fun onError(utteranceId: String?) {
                    deferred.completeExceptionally(Exception("TTS error"))
                }
            })

            val params = android.os.Bundle().apply {
                putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, runId ?: "hermes_tts")
            }
            tts!!.speak(text, TextToSpeech.QUEUE_FLUSH, params, runId ?: "hermes_tts")
            deferred.await()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "TTS speak failed: ${e.message}", cause = e))
        }
    }

    // Delegate other methods
    override suspend fun terminalExec(command: String, timeoutSeconds: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalSpawn(command: String, cwd: String?, env: Map<String, String>?, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalKill(pid: Int, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalList(runId: String?): Result<List<TerminalSession>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun fileRead(path: String, maxChars: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileWrite(path: String, content: String, append: Boolean, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileList(path: String, recursive: Boolean, runId: String?): Result<List<FileEntry>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileDelete(path: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileSearch(path: String, pattern: String, runId: String?): Result<List<FileEntry>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun systemInfo(runId: String?): Result<SystemInfo> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use system facade"))
    override suspend fun systemAction(action: String, args: Map<String, Any>?, runId: String?): Result<Any> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use system facade"))
    override suspend fun accessibilitySnapshot(limit: Int, runId: String?): Result<AccessibilitySnapshot> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use accessibility facade"))
    override suspend fun accessibilityAction(action: String, vararg args: Pair<String, Any>): Result<Any> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use accessibility facade"))
    override suspend fun projectionStart(runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use projection facade"))
    override suspend fun projectionStop(runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use projection facade"))
    override suspend fun projectionScreenshot(runId: String?): Result<ByteArray> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use projection facade"))
    override suspend fun sensorsList(runId: String?): Result<List<SensorInfo>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use sensors facade"))
    override suspend fun sensorsRead(sensorType: String, runId: String?): Result<SensorReading> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use sensors facade"))
    override suspend fun locationGet(runId: String?): Result<LocationInfo> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use sensors facade"))
    override suspend fun calendarQuery(query: String, runId: String?): Result<List<CalendarEvent>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use calendar facade"))
    override suspend fun logcatRead(filterSpec: String, maxLines: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use logcat facade"))
    override suspend fun notificationsList(limit: Int, runId: String?): Result<List<NotificationInfo>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use notifications facade"))
    override suspend fun clipboardGet(runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use clipboard facade"))
    override suspend fun clipboardSet(content: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use clipboard facade"))
    override suspend fun shareSend(content: String, mimeType: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use share facade"))
    override suspend fun sttListen(language: String?, timeoutSeconds: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use stt facade"))
    override suspend fun notificationPost(title: String, body: String, channel: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use notifications post facade"))
    override suspend fun appsList(runId: String?): Result<List<AppInfo>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use apps facade"))
    override suspend fun appsLaunch(packageName: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use apps facade"))
    override suspend fun resourcesGet(runId: String?): Result<ResourceUsage> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use resources facade"))
    override suspend fun cleanupRun(components: List<String>?, runId: String?): Result<CleanupResult> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use cleanup facade"))
}