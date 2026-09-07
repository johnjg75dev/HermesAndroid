package com.mobilefork.hermesagent.ui.chat

import android.app.Application
import android.net.Uri
import android.provider.OpenableColumns
import android.text.format.DateFormat
import android.util.Base64
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mobilefork.hermesagent.api.ChatCompletionRequest
import com.mobilefork.hermesagent.api.ChatMessage
import com.mobilefork.hermesagent.api.HermesEndpointUrl
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.api.HermesRunEventsClient
import com.mobilefork.hermesagent.api.SseEvent
import com.mobilefork.hermesagent.api.HermesSseClient
import com.mobilefork.hermesagent.api.ManageSessionSummary
import com.mobilefork.hermesagent.backend.BackendKind
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import com.mobilefork.hermesagent.backend.OnDeviceBackendManager
import com.mobilefork.hermesagent.data.ConversationStore
import com.mobilefork.hermesagent.data.AppSettings
import com.mobilefork.hermesagent.data.AppSettingsStore
import com.mobilefork.hermesagent.data.HermesNetworkPolicy
import com.mobilefork.hermesagent.data.McpPromptCacheResendPolicy
import com.mobilefork.hermesagent.data.McpSettingsStore
import com.mobilefork.hermesagent.data.ProviderPresets
import com.mobilefork.hermesagent.data.SecureSecretsStore
import com.mobilefork.hermesagent.data.StoredConversationAttachment
import com.mobilefork.hermesagent.data.StoredConversationMessage
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.URI
import java.util.UUID

private const val STREAM_PERSIST_INTERVAL_MS = 400L

class ChatViewModel(application: Application) : AndroidViewModel(application) {
    private val conversationStore = ConversationStore(application)
    private val _uiState = MutableStateFlow(
        ChatUiState(
            activeConversationId = "",
            activeConversationTitle = "Chat",
            status = "Loading…",
        ),
    )
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    @Volatile
    private var streamPersistBuffer: StringBuilder? = null
    @Volatile
    private var streamPersistSessionId: String = ""
    @Volatile
    private var streamPersistMessageId: String = ""
    @Volatile
    private var lastStreamPersistMs: Long = 0L
    @Volatile
    private var activeSendJob: Job? = null
    @Volatile
    private var activeSseClient: HermesSseClient? = null

    init {
        viewModelScope.launch(Dispatchers.IO) {
            val next = buildState()
            _uiState.update {
                next.copy(
                    input = it.input,
                    attachments = it.attachments,
                    isSending = it.isSending,
                )
            }
        }
    }

    fun updateInput(value: String) {
        _uiState.update { it.copy(input = value) }
    }

    fun attachImage(uriString: String) {
        val uri = Uri.parse(uriString)
        val details = queryAttachmentDetails(uri)
        _uiState.update { state ->
            if (state.attachments.any { it.uri == uriString }) {
                state
            } else {
                state.copy(
                    attachments = state.attachments + ChatAttachment(
                        uri = uriString,
                        displayName = details.displayName,
                        mimeType = details.mimeType,
                        sizeBytes = details.sizeBytes,
                    ),
                    status = "Image attached for multimodal Gemma requests",
                    error = "",
                )
            }
        }
    }

    fun removeAttachment(uriString: String) {
        _uiState.update { state ->
            state.copy(attachments = state.attachments.filterNot { it.uri == uriString })
        }
    }

    fun applyVoiceInput(text: String) {
        _uiState.update { state ->
            val merged = listOf(state.input.trim(), text.trim()).filter { it.isNotBlank() }.joinToString(" ")
            state.copy(input = merged, isListening = false, status = "Voice input captured", error = "")
        }
    }

    fun setListening(active: Boolean) {
        _uiState.update { it.copy(isListening = active, status = if (active) "Listening…" else it.status) }
    }

    fun setStatus(message: String) {
        _uiState.update { it.copy(status = message) }
    }

    fun clearStatus() {
        _uiState.update { it.copy(status = "") }
    }

    fun toggleIntermediateSteps() {
        _uiState.update { it.copy(showIntermediateSteps = !it.showIntermediateSteps) }
    }

    fun stopCurrentTask() {
        val snapshot = _uiState.value
        if (!snapshot.isSending) return
        activeSseClient?.cancel()
        activeRunEventsClient?.cancel()
        activeSendJob?.cancel()
        // Best-effort server-side stop for runs-API sessions.
        snapshot.pendingApproval?.runId?.let { runId ->
            viewModelScope.launch(Dispatchers.IO) {
                runCatching { clientForManageCalls().stopRun(runId) }
            }
        }
        streamPersistBuffer = null
        _uiState.update {
            it.copy(
                isSending = false,
                moaMembers = emptyList(),
                moaAggregating = false,
                pendingApproval = null,
                pendingClarify = null,
                status = "Stopped by user",
                error = "",
            )
        }
    }

    fun startNewConversation() {
        val conversation = conversationStore.createNewConversation()
        _uiState.value = buildState(
            activeConversationId = conversation.sessionId,
            messages = emptyList(),
            status = "Started a new chat",
        )
    }

    fun clearCurrentConversation() {
        val nextConversation = conversationStore.clearCurrentConversation()
        _uiState.value = buildState(
            activeConversationId = nextConversation.sessionId,
            messages = nextConversation.messages.toUiMessages(),
            status = "Cleared the previous conversation",
        )
    }

    fun showHistory() {
        _uiState.update {
            it.copy(
                isShowingHistory = true,
                conversationSummaries = loadSummaries(),
                status = "",
                error = "",
            )
        }
        refreshSessionSummariesFromRuntime()
    }

    /**
     * M04 drawer data path: SessionDB (via the manage API) is the source of
     * truth; local ConversationStore rows remain visible as a read-only cache
     * for anything not yet migrated.
     */
    private fun refreshSessionSummariesFromRuntime() {
        viewModelScope.launch(Dispatchers.IO) {
            val runtime = HermesRuntimeManager.currentState()
            if (!runtime.started) return@launch
            val endpoint = resolveChatEndpoint(runtime) ?: return@launch
            val remote = runCatching {
                HermesApiClient(
                    baseUrl = endpoint.baseUrl,
                    apiKey = endpoint.apiKey,
                    networkGuard = { url ->
                        HermesNetworkPolicy.requireExternalNetworkAllowed(
                            getApplication<Application>(),
                            url,
                            actionLabel = "session list",
                        )
                    },
                ).listManageSessions(limit = 100)
            }.getOrElse { return@launch }
            if (remote.isEmpty()) return@launch

            _uiState.update { state ->
                val remoteUi = remote.map { session -> session.toConversationSummary() }
                val remoteIds = remoteUi.map { it.id }.toSet()
                val localOnly = state.conversationSummaries.filter { it.id !in remoteIds }
                state.copy(conversationSummaries = remoteUi + localOnly)
            }
        }
    }

    fun hideHistory() {
        _uiState.update { it.copy(isShowingHistory = false) }
    }

    /** M04 drawer search filter (client-side over the merged summary list). */
    fun searchSessions(query: String) {
        val filtered = if (query.isBlank()) {
            loadSummaries()
        } else {
            val needle = query.trim().lowercase()
            loadSummaries().filter { summary ->
                summary.title.lowercase().contains(needle) ||
                    summary.preview.lowercase().contains(needle)
            }
        }
        _uiState.update {
            it.copy(sessionSearchQuery = query, conversationSummaries = filtered)
        }
        if (!query.isBlank()) {
            // Keep live results while typing against SessionDB too.
            refreshSessionSummariesFromRuntime()
        }
    }

    fun deleteSession(sessionId: String) {
        viewModelScope.launch(Dispatchers.IO) {
            runCatching {
                clientForManageCalls().deleteManageSession(sessionId)
            }
            conversationStore.deleteConversation(sessionId)
            _uiState.update { state ->
                state.copy(
                    conversationSummaries = state.conversationSummaries.filter { it.id != sessionId },
                )
            }
        }
    }

    /**
     * M04 branch action: copy a remote SessionDB session into a new resumable
     * session without mutating the original. Local cache rows are untouched.
     */
    fun branchSession(sessionId: String) {
        viewModelScope.launch(Dispatchers.IO) {
            val branched = runCatching {
                clientForManageCalls().branchManageSession(sessionId, title = null)
            }.getOrNull()
            _uiState.update {
                it.copy(
                    status = if (branched != null) {
                        "Branched into a new session"
                    } else {
                        "Branch failed — runtime unavailable"
                    },
                )
            }
            refreshSessionSummariesFromRuntime()
        }
    }

    private fun clientForManageCalls(): HermesApiClient {
        val runtime = HermesRuntimeManager.currentState()
        require(runtime.started) { "Hermes runtime not started" }
        val endpoint = resolveChatEndpoint(runtime) ?: error("No chat endpoint for manage calls")
        return HermesApiClient(
            baseUrl = endpoint.baseUrl,
            apiKey = endpoint.apiKey,
            networkGuard = { url ->
                HermesNetworkPolicy.requireExternalNetworkAllowed(
                    getApplication<Application>(),
                    url,
                    actionLabel = "manage sessions",
                )
            },
        )
    }

    // --- Runs API lifecycle (M03/M06): typed events -> UI state ---

    @Volatile
    private var activeRunEventsClient: HermesRunEventsClient? = null

    private fun runViaRunsApi(
        runId: String,
        endpoint: ChatEndpoint,
        assistantMessageId: String,
        sessionId: String,
    ) {
        val eventsClient = HermesRunEventsClient(
            baseUrl = endpoint.baseUrl,
            apiKey = endpoint.apiKey,
        )
        activeRunEventsClient = eventsClient

        fun finalize(content: String, errorText: String) {
            if (content.isNotBlank()) {
                conversationStore.updateMessageContent(
                    sessionId = sessionId,
                    messageId = assistantMessageId,
                    newContent = content,
                )
            }
            _uiState.update { state ->
                state.copy(
                    isSending = false,
                    moaMembers = emptyList(),
                    moaAggregating = false,
                    pendingApproval = null,
                    pendingClarify = null,
                    messages = state.messages.map { message ->
                        if (message.id == assistantMessageId && content.isNotBlank()) {
                            message.copy(content = content)
                        } else {
                            message
                        }
                    },
                    conversationSummaries = loadSummaries(),
                    activeConversationTitle = conversationStore.currentConversation().title,
                    error = errorText,
                    status = "",
                )
            }
            activeRunEventsClient = null
        }

        val contentBuilder = StringBuilder()
        val memberContent = mutableMapOf<Int, StringBuilder>()

        eventsClient.streamEvents(
            runId = runId,
            onEvent = { event ->
                when (event) {
                    is SseEvent.MessageDelta -> synchronized(contentBuilder) {
                        contentBuilder.append(event.delta)
                        appendToAssistantMessage(sessionId, assistantMessageId, event.delta)
                    }
                    is SseEvent.MoaMemberStart -> _uiState.update { state ->
                        state.copy(moaMembers = state.moaMembers + MoaMemberUi(
                            index = event.memberIndex,
                            model = event.model,
                            task = event.task,
                        ))
                    }
                    is SseEvent.MoaMemberDelta -> _uiState.update { state ->
                        val buffer = memberContent.getOrPut(event.memberIndex) { StringBuilder() }
                        synchronized(buffer) { buffer.append(event.delta) }
                        state.copy(moaMembers = state.moaMembers.map { member ->
                            if (member.index == event.memberIndex) {
                                member.copy(content = buffer.toString())
                            } else {
                                member
                            }
                        })
                    }
                    is SseEvent.MoaMemberDone -> _uiState.update { state ->
                        state.copy(moaMembers = state.moaMembers.map { member ->
                            if (member.index == event.memberIndex) {
                                member.copy(done = true, success = event.success)
                            } else {
                                member
                            }
                        })
                    }
                    is SseEvent.MoaAggregateStart -> _uiState.update { state ->
                        state.copy(moaAggregating = true, moaAggregatorModel = event.aggregatorModel)
                    }
                    is SseEvent.ApprovalRequest -> _uiState.update { state ->
                        state.copy(pendingApproval = PendingApprovalUi(
                            runId = event.runId,
                            approvalId = event.approvalId,
                            tool = event.tool,
                            action = event.action,
                            description = event.description,
                        ))
                    }
                    is SseEvent.ClarifyRequest -> _uiState.update { state ->
                        state.copy(pendingClarify = PendingClarifyUi(
                            runId = event.runId,
                            prompt = event.prompt,
                            choices = event.choices,
                            allowFreeText = event.allowFreeText,
                        ))
                    }
                    is SseEvent.Finish -> finalize(event.finalContent.ifBlank { contentBuilder.toString() }, "")
                    is SseEvent.Error -> finalize(contentBuilder.toString(), event.message)
                    else -> Unit
                }
            },
            onError = { message -> finalize(contentBuilder.toString(), message) },
            onClosed = {
                // Stream closed without explicit finish: keep whatever we have.
                if (_uiState.value.isSending) {
                    finalize(contentBuilder.toString(), "")
                }
            },
        )
    }

    private fun appendToAssistantMessage(sessionId: String, messageId: String, delta: String) {
        // Same throttled persistence contract as the raw streaming path.
        val now = System.currentTimeMillis()
        if (streamPersistSessionId != sessionId || streamPersistMessageId != messageId) {
            streamPersistSessionId = sessionId
            streamPersistMessageId = messageId
            streamPersistBuffer = StringBuilder(
                conversationStore.loadConversation(sessionId)
                    ?.messages
                    ?.firstOrNull { it.id == messageId }
                    ?.content
                    .orEmpty(),
            )
        }
        streamPersistBuffer?.append(delta)
        if (now - lastStreamPersistMs >= STREAM_PERSIST_INTERVAL_MS) {
            lastStreamPersistMs = now
            conversationStore.updateMessageContentInMemory(
                sessionId = sessionId,
                messageId = messageId,
                newContent = streamPersistBuffer?.toString().orEmpty(),
            )
            conversationStore.flushCacheToDisk()
        }
        _uiState.update { state ->
            state.copy(messages = state.messages.map { message ->
                if (message.id == messageId) {
                    message.copy(content = message.content + delta)
                } else {
                    message
                }
            })
        }
    }

    fun approvePending(approved: Boolean) {
        val pending = _uiState.value.pendingApproval ?: return
        viewModelScope.launch(Dispatchers.IO) {
            runCatching { clientForManageCalls().respondApproval(pending.runId, if (approved) "approve" else "deny") }
            _uiState.update { it.copy(pendingApproval = null) }
        }
    }

    fun answerPendingClarify(responseText: String) {
        val pending = _uiState.value.pendingClarify ?: return
        viewModelScope.launch(Dispatchers.IO) {
            runCatching { clientForManageCalls().answerClarify(pending.runId, responseText) }
            _uiState.update { it.copy(pendingClarify = null) }
        }
    }

    fun openConversation(sessionId: String) {
        val conversation = conversationStore.switchConversation(sessionId) ?: return
        _uiState.value = buildState(
            activeConversationId = conversation.sessionId,
            messages = conversation.messages.toUiMessages(),
            isShowingHistory = false,
            status = "Opened ${conversation.title}",
        )
    }

    fun consumeCommandResult(commandText: String, feedback: String?) {
        if (feedback.isNullOrBlank()) {
            _uiState.update { it.copy(input = "", error = "", isSending = false, status = "") }
            return
        }
        val now = System.currentTimeMillis()
        val sessionId = conversationStore.currentSessionId()
        val userMessage = ChatUiMessage(UUID.randomUUID().toString(), "user", commandText, now)
        val assistantMessage = ChatUiMessage(UUID.randomUUID().toString(), "assistant", feedback, now + 1)
        persistMessages(sessionId, userMessage, assistantMessage)
        _uiState.update {
            it.copy(
                activeConversationId = sessionId,
                activeConversationTitle = conversationStore.currentConversation().title,
                conversationSummaries = loadSummaries(),
                messages = conversationStore.currentConversationMessages().toUiMessages(),
                input = "",
                isSending = false,
                error = "",
                status = "",
            )
        }
    }

    fun latestAssistantReply(): String {
        return _uiState.value.messages.lastOrNull { it.role == "assistant" && it.content.isNotBlank() }?.content.orEmpty()
    }

    fun sendMessage() {
        val snapshot = _uiState.value
        sendPreparedMessage(text = snapshot.input.trim(), attachments = snapshot.attachments)
    }

    fun sendQuickPrompt(prompt: String) {
        val snapshot = _uiState.value
        val decision = evaluateQuickPromptSend(prompt, snapshot)
        if (!decision.shouldSend) {
            if (decision.blockedStatus != null) {
                _uiState.update { it.copy(status = decision.blockedStatus) }
            }
            return
        }
        sendPreparedMessage(text = prompt.trim(), attachments = emptyList())
    }

    fun stageMessageEdit(messageId: String) {
        val snapshot = _uiState.value
        if (snapshot.isSending) {
            _uiState.update { it.copy(status = "Wait for Hermes to finish before editing a sent message.") }
            return
        }
        val message = snapshot.messages.firstOrNull { it.id == messageId && it.role == "user" } ?: return
        _uiState.update {
            it.copy(
                input = message.content,
                attachments = message.attachments,
                status = "Editing sent message; send to resubmit.",
                error = "",
                isShowingHistory = false,
            )
        }
    }

    fun resendMessage(messageId: String) {
        val snapshot = _uiState.value
        if (snapshot.isSending) {
            return
        }
        val message = snapshot.messages.firstOrNull { it.id == messageId && it.role == "user" } ?: return
        sendPreparedMessage(text = message.content.trim(), attachments = message.attachments)
    }

    private fun sendPreparedMessage(text: String, attachments: List<ChatAttachment>) {
        val snapshot = _uiState.value
        if ((text.isEmpty() && attachments.isEmpty()) || snapshot.isSending) {
            return
        }

        _uiState.update {
            it.copy(
                isSending = true,
                error = "",
                status = "Starting Hermes runtime…",
                isShowingHistory = false,
            )
        }

        val sessionId = conversationStore.currentSessionId()
        val priorConversationMessages = buildPriorChatRequestMessages(snapshot.messages)
        val now = System.currentTimeMillis()
        val userMessage = ChatUiMessage(UUID.randomUUID().toString(), "user", text, now, attachments)
        val assistantMessageId = UUID.randomUUID().toString()
        val assistantPlaceholder = ChatUiMessage(assistantMessageId, "assistant", "", now + 1)

        // Register the job before it can run. Without LAZY start, a stop tap immediately after
        // send could arrive before activeSendJob was assigned, leaving the just-launched work
        // alive and able to re-enter the sending state.
        val sendJob = viewModelScope.launch(Dispatchers.IO, start = CoroutineStart.LAZY) {
            val runtime = ensureRuntimeReady()
            val endpoint = resolveChatEndpoint(runtime)
            if (!runtime.started || endpoint == null) {
                _uiState.update {
                    it.copy(
                        isSending = false,
                        error = runtime.error ?: "Hermes runtime is not ready",
                        status = "",
                    )
                }
                return@launch
            }
            _uiState.update {
                it.copy(
                    status = "Checking ${endpoint.debugLabel()} before sending…",
                    error = "",
                )
            }

            val userImages = runCatching { buildUserImageAttachments(attachments) }.getOrElse { error ->
                _uiState.update {
                    it.copy(
                        isSending = false,
                        error = error.message ?: error.javaClass.simpleName,
                        status = "",
                    )
                }
                return@launch
            }
            val memoryContext = ""

            persistMessages(sessionId, userMessage, assistantPlaceholder)

            // --- Runs API path: structured lifecycle (MoA cards, approvals,
            // clarifies). Falls back to raw chat-completions streaming when
            // the runtime predates /v1/runs.
            val runsStart = runCatching {
                HermesApiClient(
                    baseUrl = endpoint.baseUrl,
                    apiKey = endpoint.apiKey,
                ).startRun(input = text, sessionId = sessionId, model = endpoint.modelName)
            }.getOrNull()
            if (runsStart != null && runsStart.runId.isNotBlank()) {
                runViaRunsApi(
                    runId = runsStart.runId,
                    endpoint = endpoint,
                    assistantMessageId = assistantMessageId,
                    sessionId = sessionId,
                )
                return@launch
            }

            _uiState.update {
                it.copy(
                    activeConversationId = sessionId,
                    activeConversationTitle = conversationStore.currentConversation().title,
                    conversationSummaries = loadSummaries(),
                    messages = conversationStore.currentConversationMessages().toUiMessages(),
                    input = "",
                    attachments = emptyList(),
                    isSending = true,
                    error = "",
                    status = endpoint.streamingStatus(attachments.isNotEmpty()),
                    isShowingHistory = false,
                )
            }

            val client = HermesSseClient(
                baseUrl = endpoint.baseUrl,
                apiKey = endpoint.apiKey,
                networkGuard = { url ->
                    HermesNetworkPolicy.requireExternalNetworkAllowed(
                        getApplication<Application>(),
                        url,
                        actionLabel = "chat request",
                    )
                },
            )
            activeSseClient = client
            val appSettings = AppSettingsStore(getApplication<Application>()).load()
            val customSystemPrompt = appSettings.customSystemPrompt
            val cacheResendEnabled = McpPromptCacheResendPolicy.shouldResendCachedContext(
                providerId = endpoint.providerId,
                settings = McpSettingsStore(getApplication<Application>()).load(),
            )
            val apiMaxTokens = if (appSettings.apiGenerationKnobsEnabled) {
                AppSettings.normalizeLocalModelMaxTokens(appSettings.localModelMaxTokens).takeIf { it > 0 }
            } else {
                null
            }
            val apiTopP = if (appSettings.apiGenerationKnobsEnabled) {
                AppSettings.normalizeLocalModelTopP(appSettings.localModelTopP)
            } else {
                null
            }
            val apiTemperature = if (appSettings.apiGenerationKnobsEnabled) {
                AppSettings.normalizeLocalModelTemperature(appSettings.localModelTemperature)
            } else {
                null
            }
            val request = ChatCompletionRequest(
                model = endpoint.modelName,
                messages = buildChatRequestMessages(
                    userText = text,
                    userImages = userImages,
                    customSystemPrompt = customSystemPrompt,
                    priorMessages = priorConversationMessages,
                    memoryContext = memoryContext,
                    cacheResendEnabled = cacheResendEnabled,
                ),
                stream = true,
                sessionId = sessionId,
                maxTokens = apiMaxTokens,
                topP = apiTopP,
                temperature = apiTemperature,
            )
            runCatching {
                val onDelta: (String) -> Unit = { delta ->
                    // Keep stream buffer in memory; throttle disk writes to avoid jank.
                    if (streamPersistSessionId != sessionId || streamPersistMessageId != assistantMessageId) {
                        streamPersistSessionId = sessionId
                        streamPersistMessageId = assistantMessageId
                        streamPersistBuffer = StringBuilder(
                            conversationStore.loadConversation(sessionId)
                                ?.messages
                                ?.firstOrNull { it.id == assistantMessageId }
                                ?.content
                                .orEmpty(),
                        )
                    }
                    streamPersistBuffer?.append(delta)
                    val now = System.currentTimeMillis()
                    if (now - lastStreamPersistMs >= STREAM_PERSIST_INTERVAL_MS) {
                        lastStreamPersistMs = now
                        val snapshot = streamPersistBuffer?.toString().orEmpty()
                        conversationStore.updateMessageContentInMemory(
                            sessionId = sessionId,
                            messageId = assistantMessageId,
                            newContent = snapshot,
                        )
                        conversationStore.flushCacheToDisk()
                    }
                    _uiState.update { state ->
                        state.copy(
                            messages = state.messages.map { message ->
                                if (message.id == assistantMessageId) {
                                    message.copy(content = message.content + delta)
                                } else {
                                    message
                                }
                            },
                        )
                    }
                }
                val onComplete: () -> Unit = {
                    val assistantContent = streamPersistBuffer?.toString()
                        ?: conversationStore.loadConversation(sessionId)
                            ?.messages
                            ?.firstOrNull { it.id == assistantMessageId }
                            ?.content
                            .orEmpty()
                    if (assistantContent.isNotEmpty()) {
                        conversationStore.updateMessageContent(
                            sessionId = sessionId,
                            messageId = assistantMessageId,
                            newContent = assistantContent,
                        )
                    }
                    streamPersistBuffer = null
                    _uiState.update {
                        it.copy(
                            activeConversationTitle = conversationStore.currentConversation().title,
                            conversationSummaries = loadSummaries(),
                            isSending = false,
                            status = "",
                        )
                    }
                }
                val onError: (String) -> Unit = { error ->
                    if (_uiState.value.isSending) {
                        tryNonStreamingEndpointFallback(
                            endpoint = endpoint,
                            request = request,
                            sessionId = sessionId,
                            assistantMessageId = assistantMessageId,
                            streamError = error,
                        )
                    }
                }
                val onStatus: (String) -> Unit = { status ->
                    _uiState.update {
                        it.copy(status = "${endpoint.debugLabel()}: $status")
                    }
                }
                if (endpoint.apiMode == EndpointApiMode.RESPONSES) {
                    client.streamResponse(
                        request = request,
                        onDelta = onDelta,
                        onComplete = onComplete,
                        onError = onError,
                        onStatus = onStatus,
                    )
                } else {
                    client.streamChatCompletion(
                        request = request,
                        onDelta = onDelta,
                        onComplete = onComplete,
                        onError = onError,
                        onStatus = onStatus,
                    )
                }
            }.onFailure { error ->
                val message = error.message ?: error.javaClass.simpleName
                if (_uiState.value.isSending) {
                    tryNonStreamingEndpointFallback(
                        endpoint = endpoint,
                        request = request,
                        sessionId = sessionId,
                        assistantMessageId = assistantMessageId,
                        streamError = message,
                    )
                }
            }
        }
        activeSendJob = sendJob
        sendJob.invokeOnCompletion {
            if (activeSendJob === sendJob) activeSendJob = null
            activeSseClient = null
        }
        sendJob.start()
    }

    private fun tryNonStreamingEndpointFallback(
        endpoint: ChatEndpoint,
        request: ChatCompletionRequest,
        sessionId: String,
        assistantMessageId: String,
        streamError: String,
    ): Boolean {
        // Streaming fallback always enabled (nativeToolCalling endpoint mode removed in P0)
        _uiState.update {
            it.copy(
                status = "${endpoint.debugLabel()}: stream issue detected; retrying non-stream request…",
                error = "",
            )
        }
        return runCatching {
            val fallbackClient = HermesApiClient(
                baseUrl = endpoint.baseUrl,
                apiKey = endpoint.apiKey,
                networkGuard = { url ->
                    HermesNetworkPolicy.requireExternalNetworkAllowed(
                        getApplication<Application>(),
                        url,
                        actionLabel = "chat fallback request",
                    )
                },
            )
            val result = if (endpoint.apiMode == EndpointApiMode.RESPONSES) {
                fallbackClient.createResponse(request.copy(stream = false))
            } else {
                fallbackClient.createChatCompletion(request.copy(stream = false))
            }
            val content = if (endpoint.apiMode == EndpointApiMode.RESPONSES) {
                extractAssistantContentFromResponse(result.rawBody)
            } else {
                extractAssistantContentFromChatCompletion(result.rawBody)
            }
            require(content.isNotBlank()) {
                "Non-stream endpoint returned no assistant text"
            }
            conversationStore.updateMessageContent(
                sessionId = sessionId,
                messageId = assistantMessageId,
                newContent = content,
            )
            _uiState.update { state ->
                state.copy(
                    activeConversationTitle = conversationStore.currentConversation().title,
                    conversationSummaries = loadSummaries(),
                    messages = state.messages.map { message ->
                        if (message.id == assistantMessageId) {
                            message.copy(content = content)
                        } else {
                            message
                        }
                    },
                    isSending = false,
                    error = "",
                    status = "${endpoint.debugLabel()}: recovered with non-stream request after SSE failed.",
                )
            }
            true
        }.getOrElse { fallbackError ->
            _uiState.update {
                it.copy(
                    isSending = false,
                    error = endpoint.failureMessage(
                        "Streaming failed: $streamError. Non-stream fallback also failed: " +
                            (fallbackError.message ?: fallbackError.javaClass.simpleName),
                    ),
                    status = "",
                )
            }
            false
        }
    }

    private data class ChatEndpoint(
        val baseUrl: String,
        val apiKey: String?,
        val modelName: String,
        val apiMode: EndpointApiMode = EndpointApiMode.CHAT_COMPLETIONS,
        val providerId: String = "",
    )

    private enum class EndpointApiMode {
        CHAT_COMPLETIONS,
        RESPONSES,
    }

    private fun ChatEndpoint.streamingStatus(hasAttachments: Boolean): String {
        val action = if (hasAttachments) "Hermes is reading the image" else "Hermes is replying"
        return "$action via ${endpointHostLabel(baseUrl)}…"
    }

    private fun ChatEndpoint.failureMessage(message: String): String {
        val clean = message.ifBlank { "Endpoint request failed" }
        if (!clean.looksLikeEndpointDisconnect()) {
            return clean
        }
        return "$clean Hermes normalizes raw hosts, /v1 URLs, and /v1/chat/completions URLs, but the host must still be reachable, the model name must match the server exactly, and streaming endpoints must stay open until [DONE]."
    }

    private fun ChatEndpoint.debugLabel(): String {
        val mode = when {
            apiMode == EndpointApiMode.RESPONSES -> "responses"
            else -> "endpoint"
        }
        return "$mode ${endpointHostLabel(baseUrl)} · $modelName"
    }

    private fun String.looksLikeEndpointDisconnect(): Boolean {
        val lower = lowercase()
        return listOf("timeout", "closed", "reset", "disconnect", "unexpected end", "[done]", "sse", "stream").any { token ->
            lower.contains(token)
        }
    }

    private fun endpointHostLabel(baseUrl: String): String {
        val normalizedBaseUrl = runCatching { HermesEndpointUrl.normalizeBaseUrl(baseUrl) }.getOrDefault(baseUrl)
        return runCatching {
            val uri = URI(normalizedBaseUrl)
            val host = uri.host.orEmpty().ifBlank { normalizedBaseUrl }
            val port = uri.port.takeIf { it > 0 }?.let { ":$it" }.orEmpty()
            "$host$port"
        }.getOrDefault(normalizedBaseUrl)
            .replace("https://", "")
            .replace("http://", "")
            .take(64)
    }

    private fun resolveChatEndpoint(runtime: HermesRuntimeManager.RuntimeState): ChatEndpoint? {
        val runtimeBaseUrl = runtime.baseUrl?.takeIf { it.isNotBlank() } ?: return null
        val normalizedRuntimeBaseUrl = runCatching {
            HermesEndpointUrl.normalizeBaseUrl(runtimeBaseUrl)
        }.getOrNull() ?: return null
        return ChatEndpoint(
            baseUrl = normalizedRuntimeBaseUrl,
            apiKey = runtime.apiKey,
            modelName = runtime.modelName ?: "hermes-agent-android",
            providerId = AppSettingsStore(getApplication<Application>()).load().provider,
        )
    }

    private fun ensureRuntimeReady(): HermesRuntimeManager.RuntimeState {
        val current = HermesRuntimeManager.currentState()
        if (current.started && resolveChatEndpoint(current) != null) {
            return current
        }
        return HermesRuntimeManager.ensureStarted(getApplication())
    }

    private fun buildState(
        activeConversationId: String = conversationStore.currentSessionId(),
        messages: List<ChatUiMessage> = conversationStore.currentConversationMessages().toUiMessages(),
        isShowingHistory: Boolean = false,
        status: String = "",
    ): ChatUiState {
        val conversation = conversationStore.loadConversation(activeConversationId) ?: conversationStore.currentConversation()
        return ChatUiState(
            activeConversationId = conversation.sessionId,
            activeConversationTitle = conversation.title,
            conversationSummaries = loadSummaries(),
            isShowingHistory = isShowingHistory,
            messages = messages,
            status = status,
        )
    }

    private fun loadSummaries(): List<ChatConversationSummary> {
        return conversationStore.listConversationSummaries().map { summary ->
            ChatConversationSummary(
                id = summary.sessionId,
                title = summary.title,
                preview = summary.preview,
                updatedLabel = DateFormat.format("MMM d, HH:mm", summary.updatedAtEpochMs).toString(),
                messageCount = summary.messageCount,
            )
        }
    }

    private fun ManageSessionSummary.toConversationSummary(): ChatConversationSummary {
        return ChatConversationSummary(
            id = id,
            title = title,
            preview = preview,
            updatedLabel = if (updatedAtEpochMs > 0) {
                DateFormat.format("MMM d, HH:mm", updatedAtEpochMs).toString()
            } else {
                ""
            },
            messageCount = messageCount,
        )
    }

    private fun persistMessages(sessionId: String, vararg messages: ChatUiMessage) {
        messages.forEach { message ->
            conversationStore.upsertMessage(
                sessionId = sessionId,
                message = message.toStoredMessage(),
            )
        }
    }

    private fun ChatUiMessage.toStoredMessage(): StoredConversationMessage = StoredConversationMessage(
        id = id,
        role = role,
        content = content,
        createdAtEpochMs = createdAtEpochMs,
        attachments = attachments.map { attachment ->
            StoredConversationAttachment(
                uri = attachment.uri,
                displayName = attachment.displayName,
                mimeType = attachment.mimeType,
                sizeBytes = attachment.sizeBytes,
            )
        },
    )

    private data class AttachmentDetails(
        val displayName: String,
        val mimeType: String,
        val sizeBytes: Long,
    )

    private fun queryAttachmentDetails(uri: Uri): AttachmentDetails {
        val app = getApplication<Application>()
        var displayName = uri.lastPathSegment ?: "image"
        var sizeBytes = 0L
        if (uri.scheme == "file") {
            uri.path?.let(::File)?.let { file ->
                displayName = file.name.ifBlank { displayName }
                sizeBytes = file.length().coerceAtLeast(0L)
            }
        }
        runCatching { app.contentResolver.query(uri, null, null, null, null) }.getOrNull()?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (cursor.moveToFirst()) {
                if (nameIndex >= 0) {
                    displayName = cursor.getString(nameIndex) ?: displayName
                }
                if (sizeIndex >= 0) {
                    sizeBytes = cursor.getLong(sizeIndex).coerceAtLeast(0L)
                }
            }
        }
        val mimeType = runCatching { app.contentResolver.getType(uri) }.getOrNull().orEmpty().ifBlank {
            when (displayName.substringAfterLast('.', "").lowercase()) {
                "jpg", "jpeg" -> "image/jpeg"
                "png" -> "image/png"
                "webp" -> "image/webp"
                else -> "image/*"
            }
        }
        return AttachmentDetails(displayName = displayName, mimeType = mimeType, sizeBytes = sizeBytes)
    }

    private fun buildUserImageAttachments(attachments: List<ChatAttachment>): List<String> {
        if (attachments.isEmpty()) {
            return emptyList()
        }
        return attachments.map { attachment -> readAttachmentAsDataUrl(attachment) }
    }

    private fun readAttachmentAsDataUrl(attachment: ChatAttachment): String {
        val app = getApplication<Application>()
        val uri = Uri.parse(attachment.uri)
        val mimeType = attachment.mimeType.ifBlank {
            app.contentResolver.getType(uri).orEmpty().ifBlank { "application/octet-stream" }
        }
        val bytes = app.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            ?: throw IllegalArgumentException("Unable to read ${attachment.displayName}")
        require(bytes.isNotEmpty()) { "Selected image ${attachment.displayName} is empty" }
        return "data:$mimeType;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun List<StoredConversationMessage>.toUiMessages(): List<ChatUiMessage> {
        return map { message ->
            ChatUiMessage(
                id = message.id,
                role = message.role,
                content = message.content,
                createdAtEpochMs = message.createdAtEpochMs,
                attachments = message.attachments.map { attachment ->
                    ChatAttachment(
                        uri = attachment.uri,
                        displayName = attachment.displayName,
                        mimeType = attachment.mimeType,
                        sizeBytes = attachment.sizeBytes,
                    )
                },
            )
        }
    }
}

internal fun extractAssistantContentFromChatCompletion(rawBody: String): String {
    val root = JSONObject(rawBody)
    val choices = root.optJSONArray("choices") ?: return ""
    if (choices.length() == 0) {
        return ""
    }
    val choice = choices.optJSONObject(0) ?: return ""
    val messageContent = choice.optJSONObject("message")?.opt("content")
    val deltaContent = choice.optJSONObject("delta")?.opt("content")
    return chatCompletionContentToText(messageContent ?: deltaContent).trim()
}

internal fun extractAssistantContentFromResponse(rawBody: String): String {
    val root = JSONObject(rawBody)
    val directOutput = root.optString("output_text").trim()
    if (directOutput.isNotBlank()) {
        return directOutput
    }
    val output = root.optJSONArray("output") ?: return ""
    val chunks = mutableListOf<String>()
    for (outputIndex in 0 until output.length()) {
        val item = output.optJSONObject(outputIndex) ?: continue
        val content = item.opt("content")
        val text = when (content) {
            is JSONArray -> responseContentArrayToText(content)
            else -> chatCompletionContentToText(content)
        }.trim()
        if (text.isNotBlank()) {
            chunks += text
        }
    }
    return chunks.joinToString("\n").trim()
}

internal fun buildChatRequestMessages(
    userText: String,
    userImages: List<String> = emptyList(),
    customSystemPrompt: String = "",
    priorMessages: List<ChatMessage> = emptyList(),
    memoryContext: String = "",
    cacheResendEnabled: Boolean = false,
): List<ChatMessage> {
    val userMessage = ChatMessage(role = "user", content = userText, images = userImages)
    val persona = compactCustomSystemPrompt(
        AppSettings.normalizeCustomSystemPrompt(customSystemPrompt),
    )
    val relevantMemory = compactPromotedMemoryContext(memoryContext)
    val requestMessages = mutableListOf<ChatMessage>()
    val compactedPriorMessages = if (cacheResendEnabled) {
        priorMessages
    } else {
        compactPriorChatRequestMessages(priorMessages)
    }
    if (persona.isBlank() && relevantMemory.isBlank()) {
        requestMessages += compactedPriorMessages
        requestMessages += userMessage
        return requestMessages
    }
    requestMessages += ChatMessage(
        role = "system",
        content = buildString {
            if (persona.isNotBlank()) {
                append("User-configured agent persona/system instructions. Apply them unless they conflict ")
                append("with the current user request, Android permissions, tool truthfulness, or safety constraints:\n")
                append(persona)
            }
            if (relevantMemory.isNotBlank()) {
                if (isNotEmpty()) append("\n\n")
                append("Relevant local memory context recalled from prior conversations. Use it when it helps the current request, and ignore stale or unrelated rows:\n")
                append(relevantMemory)
            }
        },
    )
    requestMessages += compactedPriorMessages
    requestMessages += userMessage
    return requestMessages
}

private const val COMPACT_SYSTEM_PROMPT_LIMIT = 2_000
private const val COMPACT_MEMORY_CONTEXT_LIMIT = 1_500
private const val COMPACT_PRIOR_MESSAGE_LIMIT = 8_000

internal fun compactCustomSystemPrompt(prompt: String): String {
    return prompt.trim().take(COMPACT_SYSTEM_PROMPT_LIMIT)
}

internal fun compactPromotedMemoryContext(memoryContext: String): String {
    return memoryContext.trim().take(COMPACT_MEMORY_CONTEXT_LIMIT)
}

internal fun compactPriorChatRequestMessages(messages: List<ChatMessage>): List<ChatMessage> {
    return messages.map { message ->
        message.copy(content = message.content.take(COMPACT_PRIOR_MESSAGE_LIMIT))
    }.filter { message -> message.content.isNotBlank() || message.images.isNotEmpty() }
}

internal fun buildPriorChatRequestMessages(messages: List<ChatUiMessage>): List<ChatMessage> {
    return compactPriorChatRequestMessages(
        messages.mapNotNull { message ->
            if (message.role != "user" && message.role != "assistant") {
                return@mapNotNull null
            }
            val content = buildString {
                val text = message.content.trim()
                if (text.isNotBlank()) {
                    append(text)
                }
                val attachmentLabels = message.attachments.map { attachment ->
                    attachment.displayName
                        .ifBlank { attachment.mimeType }
                        .ifBlank { "attachment" }
                }
                if (attachmentLabels.isNotEmpty()) {
                    if (isNotEmpty()) append('\n')
                    append(
                        attachmentLabels.joinToString("\n") { label ->
                            "[prior turn attachment omitted: $label]"
                        },
                    )
                }
            }.trim()
            if (content.isBlank()) {
                null
            } else {
                ChatMessage(
                    role = message.role,
                    content = content,
                )
            }
        },
    )
}

private fun chatCompletionContentToText(value: Any?): String {
    if (value == null || value == JSONObject.NULL) {
        return ""
    }
    return when (value) {
        is String -> value
        is JSONArray -> buildString {
            for (index in 0 until value.length()) {
                val item = value.opt(index)
                val text = when (item) {
                    is JSONObject -> item.optString("text")
                        .ifBlank { item.optString("content") }
                    is String -> item
                    else -> item?.toString().orEmpty()
                }
                if (text.isNotBlank()) {
                    if (isNotEmpty()) append('\n')
                    append(text)
                }
            }
        }
        is JSONObject -> value.optString("text").ifBlank { value.optString("content") }
        else -> value.toString()
    }
}

private fun responseContentArrayToText(value: JSONArray): String {
    return buildString {
        for (index in 0 until value.length()) {
            val item = value.opt(index)
            val text = when (item) {
                is JSONObject -> when (item.optString("type")) {
                    "output_text", "input_text", "summary_text" -> item.optString("text")
                    else -> item.optString("text")
                        .ifBlank { item.optString("content") }
                }
                is String -> item
                else -> item?.toString().orEmpty()
            }
            if (text.isNotBlank()) {
                if (isNotEmpty()) append('\n')
                append(text)
            }
        }
    }
}
