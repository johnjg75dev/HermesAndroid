package com.mobilefork.hermesagent.api

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

class HermesApiClient(
    baseUrl: String,
    private val apiKey: String? = null,
    private val httpClient: OkHttpClient = OkHttpClient(),
    private val networkGuard: (String) -> Unit = {},
) {
    private val normalizedBaseUrl = HermesEndpointUrl.normalizeBaseUrl(baseUrl)

    fun getHealth(): HealthResponse {
        val request = requestBuilder(HermesEndpointUrl.healthUrl(normalizedBaseUrl)).get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Health request failed: ${response.code} $body" }
            val json = JSONObject(body)
            return HealthResponse(
                status = json.optString("status"),
                platform = json.optString("platform"),
            )
        }
    }

    fun listModels(): ModelsResponse {
        val request = requestBuilder(HermesEndpointUrl.modelsUrl(normalizedBaseUrl)).get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Models request failed: ${response.code} $body" }
            val json = JSONObject(body)
            val models = mutableListOf<ModelInfo>()
            val data = json.optJSONArray("data") ?: JSONArray()
            for (index in 0 until data.length()) {
                val item = data.optJSONObject(index) ?: continue
                models += ModelInfo(id = item.optString("id"))
            }
            return ModelsResponse(data = models)
        }
    }

    fun createChatCompletion(request: ChatCompletionRequest): ChatCompletionResult {
        val payload = request.toChatCompletionPayload()
        val builder = requestBuilder(HermesEndpointUrl.chatCompletionsUrl(normalizedBaseUrl))
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
        if (!request.sessionId.isNullOrBlank()) {
            builder.header(SESSION_HEADER, request.sessionId)
        }
        httpClient.newCall(builder.build()).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Chat request failed: ${response.code} $body" }
            return ChatCompletionResult(rawBody = body)
        }
    }

    fun createResponse(request: ChatCompletionRequest): ChatCompletionResult {
        val payload = request.toResponsesPayload()
        val builder = requestBuilder(HermesEndpointUrl.responsesUrl(normalizedBaseUrl))
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
        if (!request.sessionId.isNullOrBlank()) {
            builder.header(SESSION_HEADER, request.sessionId)
        }
        httpClient.newCall(builder.build()).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Responses request failed: ${response.code} $body" }
            return ChatCompletionResult(rawBody = body)
        }
    }

    fun listManageSessions(limit: Int = 50): List<ManageSessionSummary> {
        val url = normalizedBaseUrl + "/v1/manage/sessions?limit=$limit"
        val request = requestBuilder(url).get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Manage sessions request failed: ${response.code} $body" }
            return parseManageSessions(body)
        }
    }

    fun branchManageSession(sessionId: String, title: String?): String {
        val url = normalizedBaseUrl + "/v1/manage/sessions/$sessionId/branch"
        val payload = JSONObject()
        if (!title.isNullOrBlank()) {
            payload.put("title", title)
        }
        val request = requestBuilder(url)
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Branch request failed: ${response.code} $body" }
            return JSONObject(body).optString("session_id")
        }
    }

    fun deleteManageSession(sessionId: String) {
        val url = normalizedBaseUrl + "/v1/manage/sessions/$sessionId"
        val request = requestBuilder(url).delete().build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) {
                "Delete session failed: ${response.code} ${response.body?.string().orEmpty()}"
            }
        }
    }

    fun getSystemResources(): SystemResources {
        val request = requestBuilder(normalizedBaseUrl + "/v1/manage/system/resources").get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Resources request failed: ${response.code} $body" }
            return parseSystemResources(body)
        }
    }

    fun runSystemCleanup(components: List<String>? = null): CleanupSummary {
        val payload = JSONObject()
        if (!components.isNullOrEmpty()) {
            payload.put("components", JSONArray(components))
        }
        val request = requestBuilder(normalizedBaseUrl + "/v1/manage/system/cleanup")
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Cleanup request failed: ${response.code} $body" }
            val json = JSONObject(body)
            return CleanupSummary(
                freedMb = json.optDouble("freed_mb", 0.0),
                skipped = json.optJSONArray("skipped")?.let { arr ->
                    (0 until arr.length()).map { arr.optString(it) }
                } ?: emptyList(),
            )
        }
    }

    fun listCronJobs(includeDisabled: Boolean = true): List<CronJobSummary> {
        val url = normalizedBaseUrl + "/v1/manage/cron?include_disabled=" + includeDisabled
        val request = requestBuilder(url).get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Cron list failed: ${response.code} $body" }
            return parseCronJobs(body)
        }
    }

    fun pauseCronJob(jobId: String): Boolean =
        cronAction("/v1/manage/cron/$jobId/pause", "Pause failed")

    fun resumeCronJob(jobId: String): Boolean =
        cronAction("/v1/manage/cron/$jobId/resume", "Resume failed")

    fun deleteCronJob(jobId: String): Boolean {
        val request = requestBuilder("$normalizedBaseUrl/v1/manage/cron/$jobId").delete().build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "Delete job failed: ${response.code}" }
            return JSONObject(response.body?.string().orEmpty()).optBoolean("removed", false)
        }
    }

    private fun cronAction(path: String, errorLabel: String): Boolean {
        val request = requestBuilder(normalizedBaseUrl + path)
            .post("{}".toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "$errorLabel: ${response.code}" }
            return true
        }
    }

    fun getInsights(): InsightsSnapshot {
        val request = requestBuilder(normalizedBaseUrl + "/v1/manage/insights").get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "Insights request failed: ${response.code} $body" }
            return parseInsights(body)
        }
    }

    /** Generic manage-channel GET returning the raw body (palette, skills, …). */
    fun getManageJson(path: String): String {
        val request = requestBuilder(normalizedBaseUrl + path).get().build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "GET $path failed: ${response.code}" }
            return response.body?.string().orEmpty()
        }
    }

    // --- Runs API (structured run lifecycle: approvals, clarifies, MoA) ---

    fun startRun(
        input: String,
        sessionId: String?,
        model: String?,
    ): RunStart {
        val payload = JSONObject().apply {
            put("input", input)
            put("stream", true)
            if (!sessionId.isNullOrBlank()) put("session_id", sessionId)
            if (!model.isNullOrBlank()) put("model", model)
        }
        val request = requestBuilder(normalizedBaseUrl + "/v1/runs")
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful || response.code == 202) {
                "Start run failed: ${response.code} $body"
            }
            val json = JSONObject(body)
            return RunStart(
                runId = json.optString("run_id"),
                sessionId = json.optString("session_id", "").ifBlank { null },
            )
        }
    }

    fun stopRun(runId: String) {
        val request = requestBuilder("$normalizedBaseUrl/v1/runs/$runId/stop")
            .post("{}".toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "Stop run failed: ${response.code}" }
        }
    }

    fun respondApproval(runId: String, choice: String) {
        val payload = JSONObject().put("choice", choice)
        val request = requestBuilder("$normalizedBaseUrl/v1/runs/$runId/approval")
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) {
                "Approval failed: ${response.code} ${response.body?.string().orEmpty()}"
            }
        }
    }

    fun answerClarify(runId: String, responseText: String) {
        val payload = JSONObject().put("response", responseText)
        val request = requestBuilder("$normalizedBaseUrl/v1/runs/$runId/clarify")
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) {
                "Clarify failed: ${response.code} ${response.body?.string().orEmpty()}"
            }
        }
    }

    // --- Workspace files (M24) ---

    fun listWorkspaceFiles(relativePath: String): WorkspaceListing {
        val url = normalizedBaseUrl + "/v1/manage/files/list?path=" +
            java.net.URLEncoder.encode(relativePath, "UTF-8")
        val request = requestBuilder(url).get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "File list failed: ${response.code} $body" }
            val json = JSONObject(body)
            val rows = json.optJSONArray("entries") ?: JSONArray()
            return WorkspaceListing(
                path = json.optString("path", ""),
                entries = (0 until rows.length()).mapNotNull { i ->
                    rows.optJSONObject(i)?.let { row ->
                        WorkspaceEntry(
                            name = row.optString("name"),
                            isDirectory = row.optBoolean("is_directory", false),
                            sizeBytes = row.optLong("size_bytes", 0),
                        )
                    }
                },
            )
        }
    }

    fun readWorkspaceFile(relativePath: String): Pair<String, Boolean> {
        val url = normalizedBaseUrl + "/v1/manage/files/read?path=" +
            java.net.URLEncoder.encode(relativePath, "UTF-8")
        val request = requestBuilder(url).get().build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            require(response.isSuccessful) { "File read failed: ${response.code} $body" }
            val json = JSONObject(body)
            return json.optString("content", "") to json.optBoolean("truncated", false)
        }
    }

    fun writeWorkspaceFile(relativePath: String, content: String) {
        val payload = JSONObject().put("path", relativePath).put("content", content)
        val request = requestBuilder(normalizedBaseUrl + "/v1/manage/files/write")
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        httpClient.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "File write failed: ${response.code}" }
        }
    }

    private fun requestBuilder(url: String): Request.Builder {
        networkGuard(url)
        val builder = Request.Builder().url(url)
        if (!apiKey.isNullOrBlank()) {
            builder.header("Authorization", "Bearer $apiKey")
        }
        return builder
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json".toMediaType()
        const val SESSION_HEADER = "X-Hermes-Session-Id"

        /** Parses /v1/manage/sessions payloads; tolerant of missing fields. */
        fun parseManageSessions(body: String): List<ManageSessionSummary> {
            val json = JSONObject(body)
            val rows = json.optJSONArray("sessions") ?: JSONArray()
            return buildList {
                for (index in 0 until rows.length()) {
                    val row = rows.optJSONObject(index) ?: continue
                    val id = row.optString("id").orEmpty()
                    if (id.isBlank()) continue
                    // SessionDB stores epoch seconds as text; prefer last_active.
                    val updatedRaw = row.optString("last_active")
                        .ifBlank { row.optString("started_at") }
                        .replace(",", "")
                    val updatedEpochMs = updatedRaw.toDoubleOrNull()
                        ?.let { (it * 1000).toLong() }
                        ?: 0L
                    add(
                        ManageSessionSummary(
                            id = id,
                            title = row.optString("title", "").ifBlank { "Untitled" },
                            preview = row.optString("preview", ""),
                            updatedAtEpochMs = updatedEpochMs,
                            messageCount = row.optInt("message_count", 0),
                        ),
                    )
                }
            }
        }
    }
}

data class ManageSessionSummary(
    val id: String,
    val title: String,
    val preview: String,
    val updatedAtEpochMs: Long,
    val messageCount: Int,
)

/** One measured component (app/python/local-model/linux). Nulls = never fabricated. */
data class ResourceSample(
    val rssMb: Double?,
    val cpuPercent: Double?,
    val threads: Int?,
)

data class SystemResources(
    val python: ResourceSample?,
    val app: ResourceSample?,
    val localModel: ResourceSample?,
    val linuxMb: Double?,
    val gpuPercent: Double?,
    val npuPercent: Double?,
    val note: String,
)

data class CleanupSummary(
    val freedMb: Double,
    val skipped: List<String>,
)

data class CronJobSummary(
    val id: String,
    val name: String,
    val prompt: String,
    val scheduleDisplay: String,
    val paused: Boolean,
)

fun parseCronJobs(body: String): List<CronJobSummary> {
    val json = JSONObject(body)
    val rows = json.optJSONArray("jobs") ?: JSONArray()
    return buildList {
        for (index in 0 until rows.length()) {
            val row = rows.optJSONObject(index) ?: continue
            val id = row.optString("id").orEmpty()
            if (id.isBlank() || id == "unknown") continue
            add(
                CronJobSummary(
                    id = id,
                    name = row.optString("name", "").ifBlank { "Untitled job" },
                    prompt = row.optString("prompt", ""),
                    scheduleDisplay = row.optString("schedule_display", "").ifBlank { "manual" },
                    paused = row.optBoolean("paused", false),
                ),
            )
        }
    }
}

data class InsightsDailyEntry(
    val day: String,
    val runs: Long,
    val tokens: Long,
    val costUsd: Double,
)

data class InsightsModelUsage(
    val model: String,
    val runs: Long,
    val tokens: Long,
    val costUsd: Double,
)

data class RunStart(
    val runId: String,
    val sessionId: String?,
)

data class WorkspaceEntry(
    val name: String,
    val isDirectory: Boolean,
    val sizeBytes: Long,
)

data class WorkspaceListing(
    val path: String,
    val entries: List<WorkspaceEntry>,
)

data class InsightsSnapshot(
    val available: Boolean,
    val runs: Long,
    val messages: Long,
    val toolCalls: Long,
    val inputTokens: Long,
    val outputTokens: Long,
    val cacheReadTokens: Long,
    val reasoningTokens: Long,
    val costUsd: Double,
    val daily: List<InsightsDailyEntry>,
    val models: List<InsightsModelUsage>,
)

fun parseInsights(body: String): InsightsSnapshot {
    val json = JSONObject(body)
    fun longOf(key: String): Long {
        val v = json.optDouble(key, 0.0)
        return if (v.isNaN()) 0L else v.toLong()
    }
    val daily = json.optJSONArray("daily")?.let { arr ->
        (0 until arr.length()).mapNotNull { i ->
            arr.optJSONObject(i)?.let { e ->
                InsightsDailyEntry(
                    day = e.optString("day"),
                    runs = e.optLong("runs", 0),
                    tokens = e.optLong("tokens", 0),
                    costUsd = e.optDouble("cost_usd", 0.0),
                )
            }
        }
    } ?: emptyList()
    val models = json.optJSONArray("models")?.let { arr ->
        (0 until arr.length()).mapNotNull { i ->
            arr.optJSONObject(i)?.let { e ->
                InsightsModelUsage(
                    model = e.optString("model", "unknown"),
                    runs = e.optLong("runs", 0),
                    tokens = e.optLong("tokens", 0),
                    costUsd = e.optDouble("cost_usd", 0.0),
                )
            }
        }
    } ?: emptyList()
    return InsightsSnapshot(
        available = json.optBoolean("available", false),
        runs = longOf("runs"),
        messages = longOf("messages"),
        toolCalls = longOf("tool_calls"),
        inputTokens = longOf("input_tokens"),
        outputTokens = longOf("output_tokens"),
        cacheReadTokens = longOf("cache_read_tokens"),
        reasoningTokens = longOf("reasoning_tokens"),
        costUsd = json.optDouble("cost_usd", 0.0),
        daily = daily,
        models = models,
    )
}

fun parseSystemResources(body: String): SystemResources {
    val json = JSONObject(body)
    fun sample(value: Any?): ResourceSample? {
        val obj = value as? JSONObject ?: return null
        return ResourceSample(
            rssMb = if (obj.isNull("rss_mb")) null else obj.optDouble("rss_mb"),
            cpuPercent = if (obj.isNull("cpu_percent")) null else obj.optDouble("cpu_percent"),
            threads = if (obj.isNull("threads")) null else obj.optInt("threads"),
        )
    }
    fun optDoubleOrNull(key: String): Double? =
        if (json.isNull(key)) null else json.optDouble(key)
    return SystemResources(
        python = sample(json.opt("python")),
        app = sample(json.opt("app")),
        localModel = sample(json.opt("local_model")),
        linuxMb = optDoubleOrNull("linux"),
        gpuPercent = optDoubleOrNull("gpu_percent"),
        npuPercent = optDoubleOrNull("npu_percent"),
        note = json.optString("note", ""),
    )
}
