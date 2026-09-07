package com.mobilefork.hermesagent.device

import android.content.Context
import com.mobilefork.hermesagent.core.di.DeviceFacadeEntryPoint
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result
import dagger.hilt.android.EntryPointAccessors
import org.json.JSONArray
import org.json.JSONObject

/**
 * Single static dispatch bridge for the Python device facade (P2).
 *
 * Python's `hermes_android.device.kotlin_facade` calls
 * `dispatchJson(operation, payloadJson)` over Chaquopy; this object resolves
 * the Hilt-provided [DeviceFacade], runs the matching suspend method on the
 * calling (agent executor) thread, and returns a JSON envelope:
 *
 *   {"success": true, "data": <jsonable>} |
 *   {"success": false, "error_code": "...", "error_message": "..."}
 *
 * Bounded timeouts/cancellation remain the facade impls' responsibility;
 * this layer only translates the wire contract.
 */
object HermesDeviceFacadeBridge {

    @Volatile
    private var cachedFacade: DeviceFacade? = null

    @JvmStatic
    fun dispatchJson(operation: String, payloadJson: String): String {
        val payload = runCatching { JSONObject(payloadJson) }.getOrElse { JSONObject() }
        val response = try {
            val facade = resolveFacade()
            // Python agent executor threads call this synchronously; blocking
            // here is the intended contract (bounded by each facade impl).
            kotlinx.coroutines.runBlocking { dispatch(facade, operation, payload) }
        } catch (e: Throwable) {
            errorPayload("DEVICE_UNAVAILABLE", e.message ?: e.javaClass.simpleName)
        }
        return response.toString()
    }

    private fun resolveFacade(): DeviceFacade {
        cachedFacade?.let { return it }
        val context: Context = HermesApplicationHolder.context()
        val entryPoint = EntryPointAccessors.fromApplication(
            context.applicationContext,
            DeviceFacadeEntryPoint::class.java,
        )
        val facade = entryPoint.deviceFacade().get()
        cachedFacade = facade
        return facade
    }

    private suspend fun dispatch(facade: DeviceFacade, operation: String, p: JSONObject): JSONObject =
        when (operation) {
            "terminal_exec" -> toJson(
                facade.terminalExec(
                    command = p.getString("command"),
                    timeoutSeconds = p.optInt("timeout_seconds", 30),
                    runId = p.optString("run_id", "").ifBlank { null },
                ),
            )
            "terminal_spawn" -> toJson(
                facade.terminalSpawn(
                    command = p.getString("command"),
                    cwd = p.optString("cwd", "").ifBlank { null },
                    env = stringMap(p.optJSONObject("env")),
                    runId = p.optString("run_id", "").ifBlank { null },
                ),
            )
            "terminal_kill" -> toJson(
                facade.terminalKill(pid = p.getInt("pid"), runId = optRunId(p)),
            )
            "terminal_list" -> toJson(facade.terminalList(optRunId(p)))
            "file_read" -> toJson(
                facade.fileRead(
                    path = p.getString("path"),
                    maxChars = p.optInt("max_chars", 100_000),
                    runId = optRunId(p),
                ),
            )
            "file_write" -> toJson(
                facade.fileWrite(
                    path = p.getString("path"),
                    content = p.getString("content"),
                    append = p.optBoolean("append", false),
                    runId = optRunId(p),
                ),
            )
            "file_list" -> toJson(
                facade.fileList(
                    path = p.getString("path"),
                    recursive = p.optBoolean("recursive", false),
                    runId = optRunId(p),
                ),
            )
            "file_delete" -> toJson(facade.fileDelete(path = p.getString("path"), runId = optRunId(p)))
            "file_search" -> toJson(
                facade.fileSearch(
                    path = p.getString("path"),
                    pattern = p.getString("pattern"),
                    runId = optRunId(p),
                ),
            )
            "system_info" -> toJson(facade.systemInfo(optRunId(p)))
            "system_action" -> toJson(
                facade.systemAction(
                    action = p.getString("action"),
                    args = argsMap(p.optJSONObject("args")),
                    runId = optRunId(p),
                ),
            )
            "accessibility_snapshot" -> toJson(
                facade.accessibilitySnapshot(limit = p.optInt("limit", 80), runId = optRunId(p)),
            )
            "accessibility_action" -> toJson(
                facade.accessibilityAction(action = p.getString("action")),
            )
            "projection_start" -> toJson(facade.projectionStart(optRunId(p)))
            "projection_stop" -> toJson(facade.projectionStop(optRunId(p)))
            "projection_screenshot" -> toJson(facade.projectionScreenshot(optRunId(p)))
            "sensors_list" -> toJson(facade.sensorsList(optRunId(p)))
            "sensors_read" -> toJson(
                facade.sensorsRead(sensorType = p.getString("sensor_type"), runId = optRunId(p)),
            )
            "location_get" -> toJson(facade.locationGet(optRunId(p)))
            "calendar_query" -> toJson(
                facade.calendarQuery(query = p.optString("query", ""), runId = optRunId(p)),
            )
            "logcat_read" -> toJson(
                facade.logcatRead(
                    filterSpec = p.optString("filter_spec", ""),
                    maxLines = p.optInt("max_lines", 100),
                    runId = optRunId(p),
                ),
            )
            "notifications_list" -> toJson(
                facade.notificationsList(limit = p.optInt("limit", 50), runId = optRunId(p)),
            )
            "clipboard_get" -> toJson(facade.clipboardGet(optRunId(p)))
            "clipboard_set" -> toJson(
                facade.clipboardSet(content = p.getString("content"), runId = optRunId(p)),
            )
            "share_send" -> toJson(
                facade.shareSend(
                    content = p.getString("content"),
                    mimeType = p.optString("mime_type", "text/plain"),
                    runId = optRunId(p),
                ),
            )
            "tts_speak" -> toJson(
                facade.ttsSpeak(
                    text = p.getString("text"),
                    language = p.optString("language", "").ifBlank { null },
                    runId = optRunId(p),
                ),
            )
            "stt_listen" -> toJson(
                facade.sttListen(
                    language = p.optString("language", "").ifBlank { null },
                    timeoutSeconds = p.optInt("timeout_seconds", 30),
                    runId = optRunId(p),
                ),
            )
            "notification_post" -> toJson(
                facade.notificationPost(
                    title = p.getString("title"),
                    body = p.getString("body"),
                    channel = p.optString("channel", "hermes"),
                    runId = optRunId(p),
                ),
            )
            "apps_list" -> toJson(facade.appsList(optRunId(p)))
            "apps_launch" -> toJson(
                facade.appsLaunch(packageName = p.getString("package_name"), runId = optRunId(p)),
            )
            "resources_get" -> toJson(facade.resourcesGet(optRunId(p)))
            "cleanup_run" -> toJson(
                facade.cleanupRun(
                    components = p.optJSONArray("components")?.let { arr ->
                        (0 until arr.length()).mapNotNull { arr.optString(it).ifBlank { null } }
                    },
                    runId = optRunId(p),
                ),
            )
            else -> errorPayload("DEVICE_UNAVAILABLE", "Unknown facade operation '$operation'")
        }

    private fun optRunId(p: JSONObject): String? = p.optString("run_id", "").ifBlank { null }

    private fun stringMap(obj: JSONObject?): Map<String, String>? {
        obj ?: return null
        val out = mutableMapOf<String, String>()
        for (key in obj.keys()) {
            out[key] = obj.optString(key)
        }
        return out
    }

    private fun argsMap(obj: JSONObject?): Map<String, Any>? {
        obj ?: return null
        val out = mutableMapOf<String, Any>()
        for (key in obj.keys()) {
            when (val value = obj.get(key)) {
                is JSONObject, is JSONArray -> out[key] = value.toString()
                JSONObject.NULL -> Unit
                else -> out[key] = value
            }
        }
        return out
    }

    /** Kotlin Result (facade wrapper) -> wire envelope. */
    private fun toJson(result: Result<*>): JSONObject = when (result) {
        is Result.Success<*> -> JSONObject()
            .put("success", true)
            .put("data", jsonable(result.value))
        is Result.Failure -> JSONObject()
            .put("success", false)
            .put("error_code", result.failure.code)
            .put("error_message", result.failure.message)
    }

    private fun errorPayload(code: String, message: String): JSONObject = JSONObject()
        .put("success", false)
        .put("error_code", code)
        .put("error_message", message)

    private fun jsonable(value: Any?): Any = when (value) {
        null -> JSONObject.NULL
        is String, is Boolean, is Int, is Long, is Double, is Float -> value
        is JSONObject, is JSONArray -> value
        is List<*> -> JSONArray().apply { value.forEach { put(jsonable(it)) } }
        is Map<*, *> -> JSONObject().apply {
            value.forEach { (k, v) -> put(k.toString(), jsonable(v)) }
        }
        else -> value.toString()
    }
}

/** Indirection so tests can supply a fake application context. */
object HermesApplicationHolder {
    @Volatile
    var provider: () -> Context = { com.mobilefork.hermesagent.HermesApplication.instance }

    fun context(): Context = provider()
}
