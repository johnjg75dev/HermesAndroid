package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import android.content.Context
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result

class AccessibilityFacadeImpl(private val context: Context) : DeviceFacade {

    override suspend fun accessibilitySnapshot(
        limit: Int,
        runId: String?,
    ): Result<AccessibilitySnapshot> {
        return try {
            val service = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as? android.accessibilityservice.AccessibilityService
            if (service == null) {
                return Result.failure(HermesError(HermesErrorCode.PERMISSION_MISSING, "Accessibility service not enabled"))
            }

            val root = service.rootInActiveWindow
            if (root == null) {
                return Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "No active window"))
            }

            val nodes = mutableListOf<AccessibilityNode>()
            collectNodes(root, nodes, limit)

            val snapshot = AccessibilitySnapshot(
                nodes = nodes,
                timestamp = System.currentTimeMillis(),
            )
            Result.success(snapshot)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Accessibility snapshot failed: ${e.message}", cause = e))
        }
    }

    private fun collectNodes(
        node: AccessibilityNodeInfo,
        nodes: MutableList<AccessibilityNode>,
        limit: Int,
    ) {
        if (nodes.size >= limit) return

        val bounds = android.graphics.Rect()
        node.getBoundsInScreen(bounds)

        nodes.add(AccessibilityNode(
            id = node.viewIdResourceName?.hashCode() ?: System.identityHashCode(node),
            className = node.className.toString(),
            text = node.text?.toString(),
            contentDescription = node.contentDescription?.toString(),
            bounds = Rect(
                left = bounds.left,
                top = bounds.top,
                right = bounds.right,
                bottom = bounds.bottom,
            ),
            clickable = node.isClickable,
            enabled = node.isEnabled,
        ))

        for (i in 0 until node.childCount) {
            val child = node.getChild(i)
            if (child != null) {
                collectNodes(child, nodes, limit)
                child.recycle()
            }
        }
    }

    override suspend fun accessibilityAction(
        action: String,
        vararg args: Pair<String, Any>,
    ): Result<Any> {
        return try {
            val python = com.chaquo.python.Python.getInstance()
            val actionArgs = args.toMap()
            val result = python.getModule("hermes_android.device.proxy")
                .callAttr("accessibility_action", action, actionArgs.toString())
                .toString()
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Accessibility action failed: ${e.message}", cause = e))
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