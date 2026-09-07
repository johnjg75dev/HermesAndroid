package com.mobilefork.hermesagent.device.facade

import com.mobilefork.hermesagent.core.error.HermesError

interface DeviceFacade {
    // Terminal / Process
    suspend fun terminalExec(
        command: String,
        timeoutSeconds: Int = 30,
        runId: String? = null,
    ): Result<String>

    suspend fun terminalSpawn(
        command: String,
        cwd: String? = null,
        env: Map<String, String>? = null,
        runId: String? = null,
    ): Result<String>

    suspend fun terminalKill(
        pid: Int,
        runId: String? = null,
    ): Result<Unit>

    suspend fun terminalList(runId: String? = null): Result<List<TerminalSession>>

    // File I/O
    suspend fun fileRead(
        path: String,
        maxChars: Int = 100_000,
        runId: String? = null,
    ): Result<String>

    suspend fun fileWrite(
        path: String,
        content: String,
        append: Boolean = false,
        runId: String? = null,
    ): Result<Unit>

    suspend fun fileList(
        path: String,
        recursive: Boolean = false,
        runId: String? = null,
    ): Result<List<FileEntry>>

    suspend fun fileDelete(
        path: String,
        runId: String? = null,
    ): Result<Unit>

    suspend fun fileSearch(
        path: String,
        pattern: String,
        runId: String? = null,
    ): Result<List<FileEntry>>

    // System
    suspend fun systemInfo(runId: String? = null): Result<SystemInfo>

    suspend fun systemAction(
        action: String,
        args: Map<String, Any>? = null,
        runId: String? = null,
    ): Result<Any>

    // Accessibility
    suspend fun accessibilitySnapshot(
        limit: Int = 80,
        runId: String? = null,
    ): Result<AccessibilitySnapshot>

    suspend fun accessibilityAction(
        action: String,
        vararg args: Pair<String, Any>,
    ): Result<Any>

    // Projection / Screen
    suspend fun projectionStart(runId: String? = null): Result<Unit>

    suspend fun projectionStop(runId: String? = null): Result<Unit>

    suspend fun projectionScreenshot(runId: String? = null): Result<ByteArray>

    // Sensors / Location
    suspend fun sensorsList(runId: String? = null): Result<List<SensorInfo>>

    suspend fun sensorsRead(
        sensorType: String,
        runId: String? = null,
    ): Result<SensorReading>

    suspend fun locationGet(runId: String? = null): Result<LocationInfo>

    // Calendar / Logcat / Notifications
    suspend fun calendarQuery(
        query: String,
        runId: String? = null,
    ): Result<List<CalendarEvent>>

    suspend fun logcatRead(
        filterSpec: String = "",
        maxLines: Int = 100,
        runId: String? = null,
    ): Result<String>

    suspend fun notificationsList(
        limit: Int = 50,
        runId: String? = null,
    ): Result<List<NotificationInfo>>

    // Clipboard / Share
    suspend fun clipboardGet(runId: String? = null): Result<String>

    suspend fun clipboardSet(
        content: String,
        runId: String? = null,
    ): Result<Unit>

    suspend fun shareSend(
        content: String,
        mimeType: String = "text/plain",
        runId: String? = null,
    ): Result<Unit>

    // TTS / STT
    suspend fun ttsSpeak(
        text: String,
        language: String? = null,
        runId: String? = null,
    ): Result<Unit>

    suspend fun sttListen(
        language: String? = null,
        timeoutSeconds: Int = 30,
        runId: String? = null,
    ): Result<String>

    // Notifications
    suspend fun notificationPost(
        title: String,
        body: String,
        channel: String = "hermes",
        runId: String? = null,
    ): Result<Unit>

    // Apps
    suspend fun appsList(runId: String? = null): Result<List<AppInfo>>

    suspend fun appsLaunch(
        packageName: String,
        runId: String? = null,
    ): Result<Unit>

    // Resources
    suspend fun resourcesGet(runId: String? = null): Result<ResourceUsage>

    // Cleanup
    suspend fun cleanupRun(
        components: List<String>? = null,
        runId: String? = null,
    ): Result<CleanupResult>
}

// Data classes
data class TerminalSession(
    val pid: Int,
    val command: String,
    val startTime: Long,
    val status: String,
)

data class FileEntry(
    val name: String,
    val path: String,
    val isDirectory: Boolean,
    val size: Long,
    val modified: Long,
)

data class SystemInfo(
    val osVersion: String,
    val apiLevel: Int,
    val deviceModel: String,
    val manufacturer: String,
    val availableMemory: Long,
    val totalMemory: Long,
)

data class AccessibilitySnapshot(
    val nodes: List<AccessibilityNode>,
    val timestamp: Long,
)

data class AccessibilityNode(
    val id: Int,
    val className: String,
    val text: String?,
    val contentDescription: String?,
    val bounds: Rect,
    val clickable: Boolean,
    val enabled: Boolean,
)

data class Rect(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
)

data class SensorInfo(
    val name: String,
    val type: Int,
    val vendor: String,
    val maxRange: Float,
    val resolution: Float,
    val power: Float,
)

data class SensorReading(
    val sensorType: String,
    val values: FloatArray,
    val timestamp: Long,
    val accuracy: Int,
)

data class LocationInfo(
    val latitude: Double,
    val longitude: Double,
    val altitude: Double?,
    val accuracy: Float,
    val timestamp: Long,
)

data class CalendarEvent(
    val id: String,
    val title: String,
    val description: String?,
    val startTime: Long,
    val endTime: Long,
    val location: String?,
)

data class NotificationInfo(
    val packageName: String,
    val title: String,
    val text: String,
    val timestamp: Long,
    val importance: Int,
)

data class AppInfo(
    val packageName: String,
    val label: String,
    val icon: String?, // base64 encoded
    val versionName: String,
    val versionCode: Int,
)

data class ResourceUsage(
    val ramUsedMb: Long,
    val ramTotalMb: Long,
    val cpuPercent: Double,
    val gpuPercent: Double?,
    val npuPercent: Double?,
    val appMb: Long,
    val pythonMb: Long,
    val localModelMb: Long,
    val linuxSubsystemMb: Long,
)

data class CleanupResult(
    val freedMb: Long,
    val perComponent: Map<String, Long>,
    val skipped: List<String>,
)

// Result wrapper
sealed class Result<out T> {
    data class Success<out T>(val data: T) : Result<T>()
    data class Failure(val failure: HermesError) : Result<Nothing>()

    companion object {
        fun <T> success(value: T): Result<T> = Success(value)
        fun <T> failure(error: HermesError): Result<T> = Failure(error)
    }

    fun isSuccess(): Boolean = this is Success<*>
    fun isFailure(): Boolean = this is Failure

    @Suppress("UNCHECKED_CAST")
    val value: T?
        get() = (this as? Success<T>)?.data

    val error: HermesError?
        get() = (this as? Failure)?.failure
}