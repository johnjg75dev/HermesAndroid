package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import android.content.Context
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result
import java.io.File

class FileFacadeImpl(private val context: Context) : DeviceFacade {

    private val workspaceDir = File(context.filesDir, "workspace")

    init {
        workspaceDir.mkdirs()
    }

    override suspend fun fileRead(
        path: String,
        maxChars: Int,
        runId: String?,
    ): Result<String> {
        return try {
            val file = resolvePath(path)
            if (!file.exists() || !file.isFile) {
                Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "File not found: $path"))
            } else {
                val content = file.readText()
                Result.success(content.take(maxChars))
            }
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "File read failed: ${e.message}", cause = e))
        }
    }

    override suspend fun fileWrite(
        path: String,
        content: String,
        append: Boolean,
        runId: String?,
    ): Result<Unit> {
        return try {
            val file = resolvePath(path)
            file.parentFile?.mkdirs()
            if (append) {
                file.appendText(content)
            } else {
                file.writeText(content)
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "File write failed: ${e.message}", cause = e))
        }
    }

    override suspend fun fileList(
        path: String,
        recursive: Boolean,
        runId: String?,
    ): Result<List<FileEntry>> {
        return try {
            val file = resolvePath(path)
            if (!file.exists() || !file.isDirectory) {
                Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Not a directory: $path"))
            } else {
                val entries = if (recursive) {
                    file.walkTopDown()
                        .filter { it != file }
                        .map { f ->
                            FileEntry(
                                name = f.name,
                                path = f.absolutePath,
                                isDirectory = f.isDirectory,
                                size = f.length(),
                                modified = f.lastModified(),
                            )
                        }
                        .toList()
                } else {
                    file.listFiles()?.map { f ->
                        FileEntry(
                            name = f.name,
                            path = f.absolutePath,
                            isDirectory = f.isDirectory,
                            size = f.length(),
                            modified = f.lastModified(),
                        )
                    } ?: emptyList()
                }
                Result.success(entries)
            }
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "File list failed: ${e.message}", cause = e))
        }
    }

    override suspend fun fileDelete(
        path: String,
        runId: String?,
    ): Result<Unit> {
        return try {
            val file = resolvePath(path)
            if (file.isDirectory) {
                file.deleteRecursively()
            } else {
                file.delete()
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "File delete failed: ${e.message}", cause = e))
        }
    }

    override suspend fun fileSearch(
        path: String,
        pattern: String,
        runId: String?,
    ): Result<List<FileEntry>> {
        return try {
            val file = resolvePath(path)
            val regex = pattern.toRegex()
            val entries = file.walkTopDown()
                .filter { it.name.matches(regex) }
                .map { f ->
                    FileEntry(
                        name = f.name,
                        path = f.absolutePath,
                        isDirectory = f.isDirectory,
                        size = f.length(),
                        modified = f.lastModified(),
                    )
                }
                .toList()
            Result.success(entries)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "File search failed: ${e.message}", cause = e))
        }
    }

    private fun resolvePath(path: String): File {
        val candidate = File(path)
        return if (candidate.isAbsolute) {
            candidate
        } else {
            File(workspaceDir, path)
        }
    }

    // Delegate other methods
    override suspend fun terminalExec(command: String, timeoutSeconds: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalSpawn(command: String, cwd: String?, env: Map<String, String>?, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalKill(pid: Int, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalList(runId: String?): Result<List<TerminalSession>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
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
    override suspend fun cleanupRun(components: List<String>?, runId: String?): Result<CleanupResult> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use cleanup facade"))
}