package com.mobilefork.hermesagent.api

import org.json.JSONObject

/**
 * Current state of an active run.
 *
 * The state is *transient* — it changes during a run (tool dispatch, approval
 * requests, MoA member transitions, delegate spawn/done) but the prompt cache
 * baseline MUST remain stable. Kotlin must never reset the cached payload on a
 * transient change.
 */
sealed class HermesRunState {
    abstract val runId: RunId
    abstract val elapsedMs: Long

    /** Run is running but no tool has been dispatched yet. */
    data class Thinking(
        override val runId: RunId,
        override val elapsedMs: Long,
    ) : HermesRunState()

    /** A tool call is in flight. */
    data class ToolRunning(
        override val runId: RunId,
        override val elapsedMs: Long,
        val toolCallId: String,
        val tool: String,
        val label: String?,
        val emoji: String?,
    ) : HermesRunState()

    /** An approval prompt is pending user input. */
    data class AwaitingApproval(
        override val runId: RunId,
        override val elapsedMs: Long,
        val approvalId: String,
        val tool: String,
        val action: String,
        val description: String,
        val riskLevel: String?,
    ) : HermesRunState()

    /** A clarify prompt is pending user input. */
    data class AwaitingClarify(
        override val runId: RunId,
        override val elapsedMs: Long,
        val prompt: String,
        val choices: List<String>,
        val allowFreeText: Boolean,
        val timeoutSeconds: Int,
    ) : HermesRunState()

    /** MoA: a member model is running. */
    data class MoaMemberRunning(
        override val runId: RunId,
        override val elapsedMs: Long,
        val memberIndex: Int,
        val model: String,
    ) : HermesRunState()

    /** MoA: aggregation in progress. */
    data class MoaAggregating(
        override val runId: RunId,
        override val elapsedMs: Long,
        val aggregatorModel: String,
        val memberCount: Int,
    ) : HermesRunState()

    /** Delegate: a sub-agent is running. */
    data class DelegateRunning(
        override val runId: RunId,
        override val elapsedMs: Long,
        val parentTaskId: String,
        val depth: Int,
        val goal: String,
    ) : HermesRunState()

    /** Run finished successfully. */
    data class Finished(
        override val runId: RunId,
        override val elapsedMs: Long,
        val finishReason: String,
    ) : HermesRunState()

    /** Run errored. */
    data class Failed(
        override val runId: RunId,
        override val elapsedMs: Long,
        val code: String,
        val message: String,
        val retryable: Boolean,
    ) : HermesRunState()

    /** Run was stopped by user. */
    data class Stopped(
        override val runId: RunId,
        override val elapsedMs: Long,
    ) : HermesRunState()
}

/**
 * Accumulator for SSE events during a single run.
 *
 * Promotes transient events to typed state transitions without disturbing the
 * cached prompt baseline. The accumulator is consumed by the ChatViewModel.
 */
class RunStateAccumulator(val runId: RunId) {
    private val startTime = System.currentTimeMillis()
    private var _state: HermesRunState = HermesRunState.Thinking(runId, 0L)
    val state: HermesRunState get() = _state

    /** Pending tool calls: toolCallId -> { tool, label, emoji } */
    private val pendingTools = mutableMapOf<String, ToolPreview>()

    /** Pending approval prompts: approvalId -> request. */
    private val pendingApprovals = mutableMapOf<String, SseEvent.ApprovalRequest>()

    /** Pending clarify prompts: kept on state until answered. */
    private var pendingClarify: SseEvent.ClarifyRequest? = null

    /** MoA member index currently running. */
    private var activeMoaMember: Int? = null

    /** Active delegate (parent task). */
    private var activeDelegate: String? = null

    /** Last final answer text (accumulated). */
    private var finalText = StringBuilder()

    /** Whether finish event has been received. */
    var finished = false
        private set

    fun onEvent(event: SseEvent) {
        when (event) {
            is SseEvent.MessageDelta -> {
                finalText.append(event.delta)
            }

            is SseEvent.ToolProgress -> {
                if (event.status == SseEvent.ToolProgressStatus.RUNNING) {
                    pendingTools[event.toolCallId] = ToolPreview(
                        tool = event.tool,
                        label = event.label,
                        emoji = event.emoji,
                    )
                    transitionTo(HermesRunState.ToolRunning(
                        runId = runId,
                        elapsedMs = elapsed(),
                        toolCallId = event.toolCallId,
                        tool = event.tool,
                        label = event.label,
                        emoji = event.emoji,
                    ))
                } else {
                    pendingTools.remove(event.toolCallId)
                    if (pendingTools.isEmpty()) {
                        transitionTo(HermesRunState.Thinking(runId, elapsed()))
                    } else {
                        val next = pendingTools.values.first()
                        transitionTo(HermesRunState.ToolRunning(
                            runId = runId,
                            elapsedMs = elapsed(),
                            toolCallId = pendingTools.keys.first(),
                            tool = next.tool,
                            label = next.label,
                            emoji = next.emoji,
                        ))
                    }
                }
            }

            is SseEvent.ApprovalRequest -> {
                pendingApprovals[event.approvalId] = event
                transitionTo(HermesRunState.AwaitingApproval(
                    runId = runId,
                    elapsedMs = elapsed(),
                    approvalId = event.approvalId,
                    tool = event.tool,
                    action = event.action,
                    description = event.description,
                    riskLevel = event.riskLevel,
                ))
            }

            is SseEvent.ApprovalResponded -> {
                pendingApprovals.remove(event.approvalId)
                if (pendingApprovals.isEmpty()) {
                    transitionTo(HermesRunState.Thinking(runId, elapsed()))
                }
            }

            is SseEvent.ClarifyRequest -> {
                pendingClarify = event
                transitionTo(HermesRunState.AwaitingClarify(
                    runId = runId,
                    elapsedMs = elapsed(),
                    prompt = event.prompt,
                    choices = event.choices,
                    allowFreeText = event.allowFreeText,
                    timeoutSeconds = event.timeoutSeconds,
                ))
            }

            is SseEvent.ClarifyResponse -> {
                pendingClarify = null
                transitionTo(HermesRunState.Thinking(runId, elapsed()))
            }

            is SseEvent.MoaMemberStart -> {
                activeMoaMember = event.memberIndex
                transitionTo(HermesRunState.MoaMemberRunning(
                    runId = runId,
                    elapsedMs = elapsed(),
                    memberIndex = event.memberIndex,
                    model = event.model,
                ))
            }

            is SseEvent.MoaMemberDone -> {
                if (activeMoaMember == event.memberIndex) {
                    activeMoaMember = null
                }
                // After member done, expect aggregate start or back to thinking
            }

            is SseEvent.MoaAggregateStart -> {
                activeMoaMember = null
                transitionTo(HermesRunState.MoaAggregating(
                    runId = runId,
                    elapsedMs = elapsed(),
                    aggregatorModel = event.aggregatorModel,
                    memberCount = event.memberCount,
                ))
            }

            is SseEvent.DelegateStart -> {
                activeDelegate = event.parentTaskId
                transitionTo(HermesRunState.DelegateRunning(
                    runId = runId,
                    elapsedMs = elapsed(),
                    parentTaskId = event.parentTaskId,
                    depth = event.depth,
                    goal = event.goal,
                ))
            }

            is SseEvent.DelegateDone -> {
                if (activeDelegate == event.parentTaskId) {
                    activeDelegate = null
                }
                if (activeDelegate == null) {
                    transitionTo(HermesRunState.Thinking(runId, elapsed()))
                }
            }

            is SseEvent.Finish -> {
                finished = true
                transitionTo(HermesRunState.Finished(
                    runId = runId,
                    elapsedMs = elapsed(),
                    finishReason = event.finishReason,
                ))
            }

            is SseEvent.Error -> {
                finished = true
                transitionTo(HermesRunState.Failed(
                    runId = runId,
                    elapsedMs = elapsed(),
                    code = event.code,
                    message = event.message,
                    retryable = event.retryable,
                ))
            }

            is SseEvent.MoaMemberDelta -> {
                // Member delta updates the running member's content; no state transition.
                finalText.append(event.delta)
            }

            is SseEvent.Usage,
            is SseEvent.DeviceProgress,
            is SseEvent.TransientLifecycle -> {
                // No state transition for these — they are informational.
            }
        }
    }

    fun elapsed(): Long = System.currentTimeMillis() - startTime

    fun finalAnswer(): String = finalText.toString()

    private fun transitionTo(next: HermesRunState) {
        _state = next
    }

    private data class ToolPreview(
        val tool: String,
        val label: String?,
        val emoji: String?,
    )
}

/**
 * Build a transient lifecycle event from raw JSON data.
 */
fun buildTransientLifecycleEvent(eventName: String, runId: RunId, data: JSONObject): SseEvent.TransientLifecycle {
    return SseEvent.TransientLifecycle(
        runId = runId,
        timestamp = System.currentTimeMillis(),
        change = eventName,
        data = data,
    )
}
