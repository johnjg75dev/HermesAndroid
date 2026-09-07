package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result

class CompositeDeviceFacade(
    val terminal: TerminalFacadeImpl,
    val file: FileFacadeImpl,
    val system: SystemFacadeImpl,
    val accessibility: AccessibilityFacadeImpl,
    val projection: ProjectionFacadeImpl,
    val sensors: SensorsFacadeImpl,
    val calendar: CalendarFacadeImpl,
    val logcat: LogcatFacadeImpl,
    val notifications: NotificationsFacadeImpl,
    val clipboard: ClipboardFacadeImpl,
    val share: ShareFacadeImpl,
    val tts: TtsFacadeImpl,
    val stt: SttFacadeImpl,
    val notificationsPost: NotificationsPostFacadeImpl,
    val apps: AppsFacadeImpl,
    val resources: ResourcesFacadeImpl,
    val cleanup: CleanupFacadeImpl,
) : DeviceFacade {

    // Terminal / Process
    override suspend fun terminalExec(command: String, timeoutSeconds: Int, runId: String?): Result<String> =
        terminal.terminalExec(command, timeoutSeconds, runId)

    override suspend fun terminalSpawn(command: String, cwd: String?, env: Map<String, String>?, runId: String?): Result<String> =
        terminal.terminalSpawn(command, cwd, env, runId)

    override suspend fun terminalKill(pid: Int, runId: String?): Result<Unit> =
        terminal.terminalKill(pid, runId)

    override suspend fun terminalList(runId: String?): Result<List<TerminalSession>> =
        terminal.terminalList(runId)

    // File I/O
    override suspend fun fileRead(path: String, maxChars: Int, runId: String?): Result<String> =
        file.fileRead(path, maxChars, runId)

    override suspend fun fileWrite(path: String, content: String, append: Boolean, runId: String?): Result<Unit> =
        file.fileWrite(path, content, append, runId)

    override suspend fun fileList(path: String, recursive: Boolean, runId: String?): Result<List<FileEntry>> =
        file.fileList(path, recursive, runId)

    override suspend fun fileDelete(path: String, runId: String?): Result<Unit> =
        file.fileDelete(path, runId)

    override suspend fun fileSearch(path: String, pattern: String, runId: String?): Result<List<FileEntry>> =
        file.fileSearch(path, pattern, runId)

    // System
    override suspend fun systemInfo(runId: String?): Result<SystemInfo> =
        system.systemInfo(runId)

    override suspend fun systemAction(action: String, args: Map<String, Any>?, runId: String?): Result<Any> =
        system.systemAction(action, args, runId)

    // Accessibility
    override suspend fun accessibilitySnapshot(limit: Int, runId: String?): Result<AccessibilitySnapshot> =
        accessibility.accessibilitySnapshot(limit, runId)

    override suspend fun accessibilityAction(action: String, vararg args: Pair<String, Any>): Result<Any> =
        accessibility.accessibilityAction(action, *args)

    // Projection / Screen
    override suspend fun projectionStart(runId: String?): Result<Unit> =
        projection.projectionStart(runId)

    override suspend fun projectionStop(runId: String?): Result<Unit> =
        projection.projectionStop(runId)

    override suspend fun projectionScreenshot(runId: String?): Result<ByteArray> =
        projection.projectionScreenshot(runId)

    // Sensors / Location
    override suspend fun sensorsList(runId: String?): Result<List<SensorInfo>> =
        sensors.sensorsList(runId)

    override suspend fun sensorsRead(sensorType: String, runId: String?): Result<SensorReading> =
        sensors.sensorsRead(sensorType, runId)

    override suspend fun locationGet(runId: String?): Result<LocationInfo> =
        sensors.locationGet(runId)

    // Calendar / Logcat / Notifications
    override suspend fun calendarQuery(query: String, runId: String?): Result<List<CalendarEvent>> =
        calendar.calendarQuery(query, runId)

    override suspend fun logcatRead(filterSpec: String, maxLines: Int, runId: String?): Result<String> =
        logcat.logcatRead(filterSpec, maxLines, runId)

    override suspend fun notificationsList(limit: Int, runId: String?): Result<List<NotificationInfo>> =
        notifications.notificationsList(limit, runId)

    // Clipboard / Share
    override suspend fun clipboardGet(runId: String?): Result<String> =
        clipboard.clipboardGet(runId)

    override suspend fun clipboardSet(content: String, runId: String?): Result<Unit> =
        clipboard.clipboardSet(content, runId)

    override suspend fun shareSend(content: String, mimeType: String, runId: String?): Result<Unit> =
        share.shareSend(content, mimeType, runId)

    // TTS / STT
    override suspend fun ttsSpeak(text: String, language: String?, runId: String?): Result<Unit> =
        tts.ttsSpeak(text, language, runId)

    override suspend fun sttListen(language: String?, timeoutSeconds: Int, runId: String?): Result<String> =
        stt.sttListen(language, timeoutSeconds, runId)

    // Notifications
    override suspend fun notificationPost(title: String, body: String, channel: String, runId: String?): Result<Unit> =
        notificationsPost.notificationPost(title, body, channel, runId)

    // Apps
    override suspend fun appsList(runId: String?): Result<List<AppInfo>> =
        apps.appsList(runId)

    override suspend fun appsLaunch(packageName: String, runId: String?): Result<Unit> =
        apps.appsLaunch(packageName, runId)

    // Resources
    override suspend fun resourcesGet(runId: String?): Result<ResourceUsage> =
        resources.resourcesGet(runId)

    // Cleanup
    override suspend fun cleanupRun(components: List<String>?, runId: String?): Result<CleanupResult> =
        cleanup.cleanupRun(components, runId)
}