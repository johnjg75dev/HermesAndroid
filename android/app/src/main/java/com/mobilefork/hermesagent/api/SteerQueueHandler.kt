package com.mobilefork.hermesagent.api

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * Steer queue handler.
 *
 * Allows the user to submit additional input (corrections, hints, follow-up
 * requests) while a run is in flight. Server enqueues the steered message and
 * consumes it at the next natural break point (end of tool execution, end of
 * assistant turn, etc.) — never mid-stream.
 *
 * Wire: POST {baseUrl}/v1/runs/{runId}/steer  body: {"message": "..."}
 */
class SteerQueueHandler(
    private val baseUrl: String,
    private val apiKey: String?,
    private val httpClient: OkHttpClient,
) {
    /** Map of runId -> outstanding (queued but not yet consumed) steer messages. */
    private val pending = mutableMapOf<RunId, MutableList<SteerMessage>>()

    private val _events = MutableSharedFlow<SteerEvent>(extraBufferCapacity = 16)
    val events: SharedFlow<SteerEvent> = _events.asSharedFlow()

    private val _pendingCounts = MutableStateFlow<Map<RunId, Int>>(emptyMap())
    val pendingCounts: StateFlow<Map<RunId, Int>> = _pendingCounts.asStateFlow()

    /**
     * Queue a steer message for the given run.
     *
     * Returns immediately; the server may consume the message asynchronously
     * at the next safe break point. Emits a [SteerEvent.Queued] event.
     */
    fun enqueue(runId: RunId, message: String, scope: CoroutineScope) {
        val normalizedBaseUrl = HermesEndpointUrl.normalizeBaseUrl(baseUrl)
        val url = "$normalizedBaseUrl/v1/runs/$runId/steer"

        synchronized(pending) {
            val queue = pending.getOrPut(runId) { mutableListOf() }
            queue.add(SteerMessage(text = message, queuedAt = System.currentTimeMillis()))
            _pendingCounts.value = pending.mapValues { it.value.size }
        }

        scope.launch(Dispatchers.IO) {
            try {
                val payload = JSONObject().apply {
                    put("message", message)
                    put("bridge_version", BRIDGE_VERSION)
                }
                val builder = Request.Builder()
                    .url(url)
                    .header("Content-Type", "application/json")
                    .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
                if (!apiKey.isNullOrBlank()) {
                    builder.header("Authorization", "Bearer $apiKey")
                }
                val response = httpClient.newCall(builder.build()).execute()
                response.use {
                    if (response.isSuccessful) {
                        _events.emit(SteerEvent.Queued(runId, message))
                    } else {
                        // Drop the queued message — server rejected it
                        synchronized(pending) {
                            pending[runId]?.removeAll { it.text == message }
                            _pendingCounts.value = pending.mapValues { it.value.size }
                        }
                        _events.emit(SteerEvent.Rejected(runId, message, response.code))
                    }
                }
            } catch (e: Exception) {
                _events.emit(SteerEvent.Failed(runId, message, e.message ?: e.javaClass.simpleName))
            }
        }
    }

    /**
     * Mark all pending steer messages for a run as consumed.
     * Called when the server emits a "steer.consumed" event.
     */
    fun markConsumed(runId: RunId, count: Int = -1) {
        synchronized(pending) {
            val queue = pending[runId] ?: return
            if (count < 0) {
                queue.clear()
            } else {
                repeat(count.coerceAtMost(queue.size)) { queue.removeAt(0) }
            }
            _pendingCounts.value = pending.mapValues { it.value.size }
        }
    }

    /**
     * Clear all pending steer messages for a run (e.g., on stop / error).
     */
    fun clear(runId: RunId) {
        synchronized(pending) {
            pending.remove(runId)
            _pendingCounts.value = pending.mapValues { it.value.size }
        }
    }

    fun pendingCount(runId: RunId): Int = synchronized(pending) {
        pending[runId]?.size ?: 0
    }

    data class SteerMessage(
        val text: String,
        val queuedAt: Long,
    )

    sealed class SteerEvent {
        abstract val runId: RunId

        data class Queued(
            override val runId: RunId,
            val message: String,
        ) : SteerEvent()

        data class Rejected(
            override val runId: RunId,
            val message: String,
            val statusCode: Int,
        ) : SteerEvent()

        data class Failed(
            override val runId: RunId,
            val message: String,
            val errorMessage: String,
        ) : SteerEvent()
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
    }
}
