package com.mobilefork.hermesagent.api

import org.json.JSONArray
import org.json.JSONObject

/**
 * Wire-protocol version (must match Python BRIDGE_VERSION).
 * Increment when on-wire payload schema changes.
 */
const val BRIDGE_VERSION = 1

/**
 * Run identifier — opaque, server-issued. Used for:
 * - steer queue routing (POST /v1/runs/{id}/steer)
 * - approval flow (POST /v1/runs/{id}/approval)
 * - stop (POST /v1/runs/{id}/stop)
 * - SSE event correlation (run_id field on every event)
 */
typealias RunId = String

/**
 * Stable event-type names from the SSE stream.
 * Must match `SSEEventType` in hermes_android/api/events.py.
 */
object SSEEventTypes {
    // Standard gateway events
    const val MESSAGE_DELTA = "message_delta"
    const val TOOL_PROGRESS = "hermes.tool.progress"
    const val APPROVAL_REQUEST = "approval.request"
    const val APPROVAL_RESPONDED = "approval.responded"
    const val USAGE = "usage"
    const val FINISH = "finish"
    const val ERROR = "error"

    // Android-specific events
    const val CLARIFY_REQUEST = "clarify.request"
    const val CLARIFY_RESPONSE = "clarify.response"
    const val MOA_MEMBER_START = "moa.member.start"
    const val MOA_MEMBER_DELTA = "moa.member.delta"
    const val MOA_MEMBER_DONE = "moa.member.done"
    const val MOA_AGGREGATE_START = "moa.aggregate.start"
    const val DELEGATE_START = "delegate.start"
    const val DELEGATE_DONE = "delegate.done"
    const val DEVICE_PROGRESS = "device.progress"
}

/**
 * Decoded SSE event.
 */
sealed class SseEvent {
    abstract val runId: RunId
    abstract val timestamp: Long

    data class MessageDelta(
        override val runId: RunId,
        override val timestamp: Long,
        val delta: String,
    ) : SseEvent()

    data class ToolProgress(
        override val runId: RunId,
        override val timestamp: Long,
        val tool: String,
        val emoji: String?,
        val label: String?,
        val toolCallId: String,
        val status: ToolProgressStatus,
    ) : SseEvent()

    enum class ToolProgressStatus { RUNNING, COMPLETED }

    data class ApprovalRequest(
        override val runId: RunId,
        override val timestamp: Long,
        val approvalId: String,
        val tool: String,
        val action: String,
        val description: String,
        val riskLevel: String?,
    ) : SseEvent()

    data class ApprovalResponded(
        override val runId: RunId,
        override val timestamp: Long,
        val approvalId: String,
        val approved: Boolean,
    ) : SseEvent()

    data class Usage(
        override val runId: RunId,
        override val timestamp: Long,
        val promptTokens: Long,
        val completionTokens: Long,
        val totalTokens: Long,
    ) : SseEvent()

    data class Finish(
        override val runId: RunId,
        override val timestamp: Long,
        val finishReason: String,
        val finalContent: String,
    ) : SseEvent()

    data class Error(
        override val runId: RunId,
        override val timestamp: Long,
        val code: String,
        val message: String,
        val retryable: Boolean,
    ) : SseEvent()

    // Android-specific events

    data class ClarifyRequest(
        override val runId: RunId,
        override val timestamp: Long,
        val prompt: String,
        val choices: List<String>,
        val allowFreeText: Boolean,
        val timeoutSeconds: Int,
    ) : SseEvent()

    data class ClarifyResponse(
        override val runId: RunId,
        override val timestamp: Long,
        val response: String,
    ) : SseEvent()

    data class MoaMemberStart(
        override val runId: RunId,
        override val timestamp: Long,
        val memberIndex: Int,
        val model: String,
        val task: String,
    ) : SseEvent()

    data class MoaMemberDelta(
        override val runId: RunId,
        override val timestamp: Long,
        val memberIndex: Int,
        val delta: String,
    ) : SseEvent()

    data class MoaMemberDone(
        override val runId: RunId,
        override val timestamp: Long,
        val memberIndex: Int,
        val content: String,
        val success: Boolean,
        val error: String?,
    ) : SseEvent()

    data class MoaAggregateStart(
        override val runId: RunId,
        override val timestamp: Long,
        val aggregatorModel: String,
        val memberCount: Int,
    ) : SseEvent()

    data class DelegateStart(
        override val runId: RunId,
        override val timestamp: Long,
        val parentTaskId: String,
        val depth: Int,
        val goal: String,
    ) : SseEvent()

    data class DelegateDone(
        override val runId: RunId,
        override val timestamp: Long,
        val parentTaskId: String,
        val depth: Int,
        val summary: String,
        val success: Boolean,
    ) : SseEvent()

    data class DeviceProgress(
        override val runId: RunId,
        override val timestamp: Long,
        val toolCallId: String,
        val operation: String,
        val progress: Float,
        val message: String,
    ) : SseEvent()

    /**
     * Transient lifecycle event (mid-run state change).
     * Kotlin should reconcile without disturbing the cached prompt baseline.
     */
    data class TransientLifecycle(
        override val runId: RunId,
        override val timestamp: Long,
        val change: String, // "tool_dispatch", "tool_done", "moa_start", etc.
        val data: JSONObject?,
    ) : SseEvent()
}

/**
 * Decoder for raw SSE event payloads into typed SseEvent instances.
 * Returns null when the payload is malformed or for unknown event types.
 */
object SseEventDecoder {

    fun decode(eventName: String, data: JSONObject): SseEvent? {
        val runId = data.optString("run_id", "").ifBlank { return null }
        val timestamp = data.optLong("timestamp", System.currentTimeMillis())

        return when (eventName) {
            SSEEventTypes.MESSAGE_DELTA -> SseEvent.MessageDelta(
                runId = runId,
                timestamp = timestamp,
                delta = data.optString("delta"),
            )

            SSEEventTypes.TOOL_PROGRESS -> {
                val status = when (data.optString("status")) {
                    "running" -> SseEvent.ToolProgressStatus.RUNNING
                    else -> SseEvent.ToolProgressStatus.COMPLETED
                }
                SseEvent.ToolProgress(
                    runId = runId,
                    timestamp = timestamp,
                    tool = data.optString("tool"),
                    emoji = data.optString("emoji").takeIf { it.isNotBlank() },
                    label = data.optString("label").takeIf { it.isNotBlank() },
                    toolCallId = data.optString("toolCallId"),
                    status = status,
                )
            }

            SSEEventTypes.APPROVAL_REQUEST -> SseEvent.ApprovalRequest(
                runId = runId,
                timestamp = timestamp,
                approvalId = data.optString("approval_id"),
                tool = data.optString("tool"),
                action = data.optString("action"),
                description = data.optString("description"),
                riskLevel = data.optString("risk_level").takeIf { it.isNotBlank() },
            )

            SSEEventTypes.APPROVAL_RESPONDED -> SseEvent.ApprovalResponded(
                runId = runId,
                timestamp = timestamp,
                approvalId = data.optString("approval_id"),
                approved = data.optBoolean("approved"),
            )

            SSEEventTypes.USAGE -> SseEvent.Usage(
                runId = runId,
                timestamp = timestamp,
                promptTokens = data.optLong("prompt_tokens"),
                completionTokens = data.optLong("completion_tokens"),
                totalTokens = data.optLong("total_tokens"),
            )

            SSEEventTypes.FINISH -> SseEvent.Finish(
                runId = runId,
                timestamp = timestamp,
                finishReason = data.optString("finish_reason"),
                finalContent = data.optString("content"),
            )

            SSEEventTypes.ERROR -> SseEvent.Error(
                runId = runId,
                timestamp = timestamp,
                code = data.optString("code"),
                message = data.optString("message"),
                retryable = data.optBoolean("retryable"),
            )

            SSEEventTypes.CLARIFY_REQUEST -> SseEvent.ClarifyRequest(
                runId = runId,
                timestamp = timestamp,
                prompt = data.optString("prompt"),
                choices = data.optJSONArray("choices")?.let { arr ->
                    (0 until arr.length()).map { arr.optString(it) }
                } ?: emptyList(),
                allowFreeText = data.optBoolean("allow_free_text", true),
                timeoutSeconds = data.optInt("timeout_seconds", 120),
            )

            SSEEventTypes.CLARIFY_RESPONSE -> SseEvent.ClarifyResponse(
                runId = runId,
                timestamp = timestamp,
                response = data.optString("response"),
            )

            SSEEventTypes.MOA_MEMBER_START -> SseEvent.MoaMemberStart(
                runId = runId,
                timestamp = timestamp,
                memberIndex = data.optInt("member_index"),
                model = data.optString("model"),
                task = data.optString("task"),
            )

            SSEEventTypes.MOA_MEMBER_DELTA -> SseEvent.MoaMemberDelta(
                runId = runId,
                timestamp = timestamp,
                memberIndex = data.optInt("member_index"),
                delta = data.optString("delta"),
            )

            SSEEventTypes.MOA_MEMBER_DONE -> SseEvent.MoaMemberDone(
                runId = runId,
                timestamp = timestamp,
                memberIndex = data.optInt("member_index"),
                content = data.optString("content"),
                success = data.optBoolean("success"),
                error = data.optString("error").takeIf { it.isNotBlank() },
            )

            SSEEventTypes.MOA_AGGREGATE_START -> SseEvent.MoaAggregateStart(
                runId = runId,
                timestamp = timestamp,
                aggregatorModel = data.optString("aggregator_model"),
                memberCount = data.optInt("member_count"),
            )

            SSEEventTypes.DELEGATE_START -> SseEvent.DelegateStart(
                runId = runId,
                timestamp = timestamp,
                parentTaskId = data.optString("parent_task_id"),
                depth = data.optInt("depth"),
                goal = data.optString("goal"),
            )

            SSEEventTypes.DELEGATE_DONE -> SseEvent.DelegateDone(
                runId = runId,
                timestamp = timestamp,
                parentTaskId = data.optString("parent_task_id"),
                depth = data.optInt("depth"),
                summary = data.optString("summary"),
                success = data.optBoolean("success"),
            )

            SSEEventTypes.DEVICE_PROGRESS -> SseEvent.DeviceProgress(
                runId = runId,
                timestamp = timestamp,
                toolCallId = data.optString("tool_call_id"),
                operation = data.optString("operation"),
                progress = data.optDouble("progress", 0.0).toFloat(),
                message = data.optString("message"),
            )

            else -> null // Unknown event type — ignore gracefully
        }
    }
}

/**
 * Chat-completion request payload with optional run-tracking + bridge version.
 */
data class ChatCompletionRequest(
    val model: String,
    val messages: List<ChatMessage>,
    val stream: Boolean = true,
    val sessionId: String? = null,
    val runId: RunId? = null,
    val bridgeVersion: Int = BRIDGE_VERSION,
    val temperature: Float? = null,
    val topP: Float? = null,
    val maxTokens: Int? = null,
    val systemPromptOverride: String? = null,
) {
    fun toJsonObject(): JSONObject {
        val obj = JSONObject().apply {
            put("model", model)
            put("stream", stream)
            put("bridge_version", bridgeVersion)
            if (!sessionId.isNullOrBlank()) put("session_id", sessionId)
            if (!runId.isNullOrBlank()) put("run_id", runId)
            if (temperature != null) put("temperature", temperature.toDouble())
            if (topP != null) put("top_p", topP.toDouble())
            if (maxTokens != null) put("max_tokens", maxTokens)
            if (!systemPromptOverride.isNullOrBlank()) put("ephemeral_system_prompt", systemPromptOverride)
            put(
                "messages",
                JSONArray().apply {
                    messages.forEach { msg -> put(msg.toJsonObject()) }
                }
            )
        }
        return obj
    }
}

data class HealthResponse(val status: String, val platform: String)

data class ModelInfo(val id: String)
data class ModelsResponse(val data: List<ModelInfo>)

data class ChatCompletionResult(val rawBody: String)

fun ChatCompletionRequest.toChatCompletionPayload(): JSONObject {
    return toJsonObject()
}

fun ChatCompletionRequest.toResponsesPayload(): JSONObject {
    return JSONObject().apply {
        put("model", model)
        put("stream", stream)
        put("store", false)
        put("bridge_version", bridgeVersion)
        maxTokens?.takeIf { it > 0 }?.let { put("max_output_tokens", it) }
        temperature?.let { put("temperature", it.toDouble()) }
        topP?.let { put("top_p", it.toDouble()) }
        if (!sessionId.isNullOrBlank()) put("session_id", sessionId)
        if (!runId.isNullOrBlank()) put("run_id", runId)
        put(
            "input",
            JSONArray().apply {
                messages.forEach { msg ->
                    put(msg.toResponsesInputObject())
                }
            },
        )
    }
}

private fun ChatMessage.toResponsesInputObject(): JSONObject {
    return JSONObject().apply {
        put("role", role)
        if (images.isEmpty()) {
            put("content", content)
        } else {
            // Responses-API typed input content
            put(
                "content",
                JSONArray().apply {
                    if (content.isNotBlank()) {
                        put(
                            JSONObject()
                                .put("type", "input_text")
                                .put("text", content),
                        )
                    }
                    images.forEach { imageUrl ->
                        put(
                            JSONObject()
                                .put("type", "input_image")
                                .put("image_url", imageUrl),
                        )
                    }
                },
            )
        }
    }
}

data class ChatMessage(
    val role: String,
    val content: String,
    val images: List<String> = emptyList(),
) {
    fun toJsonObject(): JSONObject {
        val obj = JSONObject().apply {
            put("role", role)
            if (images.isEmpty()) {
                put("content", content)
            } else {
                // Multimodal content array
                val parts = JSONArray().apply {
                    put(JSONObject().apply {
                        put("type", "text")
                        put("text", content)
                    })
                    images.forEach { imageUrl ->
                        put(JSONObject().apply {
                            put("type", "image_url")
                            put("image_url", JSONObject().apply {
                                put("url", imageUrl)
                            })
                        })
                    }
                }
                put("content", parts)
            }
        }
        return obj
    }
}
