package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import android.app.ActivityManager
import android.content.Context
import android.os.Debug
import android.os.StatFs
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result
import java.io.File

class ResourcesFacadeImpl(private val context: Context) : DeviceFacade {

    override suspend fun resourcesGet(runId: String?): Result<ResourceUsage> {
        return try {
            val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val memInfo = ActivityManager.MemoryInfo()
            activityManager.getMemoryInfo(memInfo)

            val ramTotalMb = memInfo.totalMem / (1024 * 1024)
            val ramUsedMb = ramTotalMb - (memInfo.availMem / (1024 * 1024))

            // Get CPU usage (simplified)
            val cpuPercent = getCpuUsage()

            // Estimate app memory
            val appMb = (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / (1024 * 1024)

            // Python memory (estimated)
            val pythonMb = estimatePythonMemory()

            // Local model memory (estimated)
            val localModelMb = estimateLocalModelMemory()

            // Linux subsystem memory (estimated)
            val linuxSubsystemMb = estimateLinuxSubsystemMemory()

            val usage = ResourceUsage(
                ramUsedMb = ramUsedMb,
                ramTotalMb = ramTotalMb,
                cpuPercent = cpuPercent,
                gpuPercent = null, // Not available via public API
                npuPercent = null, // Not available via public API
                appMb = appMb,
                pythonMb = pythonMb,
                localModelMb = localModelMb,
                linuxSubsystemMb = linuxSubsystemMb,
            )
            Result.success(usage)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.RESOURCE_GAUGE_FAILED, "Resources get failed: ${e.message}", cause = e))
        }
    }

    private fun getCpuUsage(): Double {
        // Simplified CPU usage calculation
        val totalCpuTime = getTotalCpuTime()
        val appCpuTime = getAppCpuTime()
        if (totalCpuTime > 0) {
            return (appCpuTime.toDouble() / totalCpuTime.toDouble()) * 100
        }
        return 0.0
    }

    private fun getTotalCpuTime(): Long {
        // Read from /proc/stat
        return try {
            File("/proc/stat").readText().lines().first().split("\\s+".toRegex())
                .drop(1).take(7).sumOf { it.toLong() }
        } catch (e: Exception) {
            1L
        }
    }

    private fun getAppCpuTime(): Long {
        // Read from /proc/self/stat
        return try {
            val parts = File("/proc/self/stat").readText().split("\\s+".toRegex())
            parts[13].toLong() + parts[14].toLong() // utime + stime
        } catch (e: Exception) {
            0L
        }
    }

    private fun estimatePythonMemory(): Long {
        // Estimate based on Chaquopy process memory
        val memInfo = ActivityManager.MemoryInfo()
        (context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(memInfo)
        return (memInfo.totalMem / 1024 / 1024 / 4).coerceAtLeast(100).coerceAtMost(1024)
    }

    private fun estimateLocalModelMemory(): Long {
        // Estimate based on downloaded models
        val modelsDir = File(context.filesDir, "models")
        if (!modelsDir.exists()) return 0
        return modelsDir.walkTopDown()
            .filter { it.isFile }
            .sumOf { it.length() } / (1024 * 1024)
    }

    private fun estimateLinuxSubsystemMemory(): Long {
        // Estimate Linux subsystem memory
        val linuxDir = File(context.filesDir, "hermes-home/linux")
        if (!linuxDir.exists()) return 0
        return 50 // Rough estimate in MB
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
    override suspend fun cleanupRun(components: List<String>?, runId: String?): Result<CleanupResult> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use cleanup facade"))
}