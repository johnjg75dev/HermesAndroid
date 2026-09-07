package com.mobilefork.hermesagent.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Subscribes to GET /v1/runs/{run_id}/events (SSE) and emits typed
 * [SseEvent]s decoded by [SseEventDecoder]. One subscription per run;
 * [cancel] closes the connection and stops the reader thread.
 */
class HermesRunEventsClient(
    baseUrl: String,
    private val apiKey: String?,
    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build(),
) {
    private val normalizedBaseUrl = HermesEndpointUrl.normalizeBaseUrl(baseUrl)

    @Volatile
    private var call: okhttp3.Call? = null

    fun cancel() {
        call?.cancel()
    }

    fun streamEvents(
        runId: String,
        onEvent: (SseEvent) -> Unit,
        onError: (String) -> Unit,
        onClosed: () -> Unit,
    ) {
        val request = Request.Builder()
            .url("$normalizedBaseUrl/v1/runs/$runId/events")
            .apply {
                if (!apiKey.isNullOrBlank()) header("Authorization", "Bearer $apiKey")
            }
            .get()
            .build()

        val executing = httpClient.newCall(request)
        call = executing
        Thread {
            try {
                executing.execute().use { response ->
                    if (!response.isSuccessful) {
                        onError("Run events stream failed: ${response.code}")
                        return@use
                    }
                    val source = response.body?.source()
                    if (source == null) {
                        onError("Run events stream returned an empty body")
                        return@use
                    }
                    while (!source.exhausted()) {
                        val line = source.readUtf8Line() ?: break
                        if (line.startsWith(":")) continue // keepalive / stream closed
                        if (!line.startsWith("data:")) continue
                        val payload = line.removePrefix("data:").trim()
                        if (payload.isEmpty() || payload == "[DONE]") continue
                        val json = runCatching { JSONObject(payload) }.getOrNull() ?: continue
                        val eventName = json.optString("event", "")
                        val decoded = SseEventDecoder.decode(eventName, json)
                            ?: buildTransientLifecycleEvent(eventName, json.optString("run_id", ""), json)
                        onEvent(decoded)
                    }
                }
                onClosed()
            } catch (e: Exception) {
                if (executing.isCanceled()) {
                    onClosed()
                } else {
                    onError(e.message ?: e.javaClass.simpleName)
                }
            }
        }.apply {
            name = "hermes-run-events-$runId"
            isDaemon = true
            start()
        }
    }

    companion object {
        /** Blocking helper used by the ViewModel worker coroutine. */
        suspend fun <T> io(block: suspend () -> T): T = withContext(Dispatchers.IO) { block() }
    }
}
