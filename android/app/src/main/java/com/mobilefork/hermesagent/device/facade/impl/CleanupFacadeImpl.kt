package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import android.content.Context
import android.os.Debug
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class CleanupFacadeImpl(private val context: Context) : DeviceFacade {

    override suspend fun cleanupRun(
        components: List<String>?,
        runId: String?,
    ): Result<CleanupResult> {
        return withContext(Dispatchers.IO) {
            val targetComponents = components ?: listOf(
                "python_gc",
                "aux_clients",
                "tool_results",
                "kotlin_caches",
                "model_context",
                "subsystem_shells",
            )

            val perComponent = mutableMapOf<String, Long>()
            val skipped = mutableListOf<String>()
            var totalFreedMb = 0L

            for (component in targetComponents) {
                try {
                    val freed = when (component) {
                        "python_gc" -> cleanupPythonGc()
                        "aux_clients" -> cleanupAuxClients()
                        "tool_results" -> cleanupToolResults()
                        "kotlin_caches" -> cleanupKotlinCaches()
                        "model_context" -> cleanupModelContext()
                        "subsystem_shells" -> cleanupSubsystemShells()
                        else -> {
                            skipped.add(component)
                            0L
                        }
                    }
                    perComponent[component] = freed
                    totalFreedMb += freed
                } catch (e: Exception) {
                    skipped.add(component)
                }
            }

            Result.success(CleanupResult(
                freedMb = totalFreedMb,
                perComponent = perComponent.toMap(),
                skipped = skipped.toList(),
            ))
        }
    }

    private fun cleanupPythonGc(): Long {
        val before = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()
        System.gc()
        System.runFinalization()
        Thread.sleep(100)
        val after = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()
        return (before - after) / (1024 * 1024).coerceAtLeast(0)
    }

    private fun cleanupAuxClients(): Long {
        // Drop idle auxiliary clients - this would call Python side
        return 0L
    }

    private fun cleanupToolResults(): Long {
        // Trim tool-result storage
        return 0L
    }

    private fun cleanupKotlinCaches(): Long {
        val before = getCacheSize()
        clearCaches()
        val after = getCacheSize()
        return (before - after) / (1024 * 1024).coerceAtLeast(0)
    }

    private fun cleanupModelContext(): Long {
        // Unload idle local-model context (server kept warm until 15 min idle)
        return 0L
    }

    private fun cleanupSubsystemShells(): Long {
        // Kill orphan/idle subsystem shells
        return 0L
    }

    private fun getCacheSize(): Long {
        return try {
            context.cacheDir.walkTopDown()
                .filter { it.isFile }
                .sumOf { it.length() }
        } catch (e: Exception) {
            0L
        }
    }

    private fun clearCaches() {
        try {
            context.cacheDir.deleteRecursively()
            context.codeCacheDir.deleteRecursively()
            context.noBackupFilesDir.deleteRecursively()
        } catch (e: Exception) {
            // Ignore
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
    override suspend fun ttsSpeak(text: String, language: String?, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use tts facade"))
    override suspend fun sttListen(language: String?, timeoutSeconds: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use stt facade"))
    override suspend fun notificationPost(title: String, body: String, channel: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use notifications post facade"))
    override suspend fun appsList(runId: String?): Result<List<AppInfo>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use apps facade"))
    override suspend fun appsLaunch(packageName: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use apps facade"))
    override suspend fun resourcesGet(runId: String?): Result<ResourceUsage> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use resources facade"))
}