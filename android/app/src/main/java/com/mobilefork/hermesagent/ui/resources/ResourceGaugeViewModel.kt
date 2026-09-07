package com.mobilefork.hermesagent.ui.resources

import android.app.Application
import android.os.Debug
import android.os.Process
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mobilefork.hermesagent.api.CleanupSummary
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.api.ResourceSample
import com.mobilefork.hermesagent.api.SystemResources
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.atomic.AtomicReference

/**
 * Polls /v1/manage/system/resources for the chat app-bar gauge chip.
 *
 * Cadence per plan decision 8: 5 s for the collapsed chip, 2 s while the
 * detail sheet is expanded. GPU/NPU rows render only when the backend
 * self-reports; numbers are never fabricated.
 */
class ResourceGaugeViewModel(application: Application) : AndroidViewModel(application) {

    data class State(
        val enabled: Boolean = false,
        val expanded: Boolean = false,
        val resources: SystemResources? = null,
        val appRssMb: Double? = null,
        val busy: Boolean = false,
        val cleanupResult: CleanupSummary? = null,
        val error: String = "",
    )

    private val clientRef = AtomicReference<HermesApiClient?>(null)
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    private var pollJob: Job? = null

    fun setEnabled(enabled: Boolean) {
        _state.update { it.copy(enabled = enabled) }
        if (enabled) startPolling(pollMs()) else stopPolling()
    }

    fun setExpanded(expanded: Boolean) {
        _state.update { it.copy(expanded = expanded) }
        if (_state.value.enabled) {
            stopPolling()
            if (expanded) startPolling(EXPANDED_POLL_MS) else startPolling(CHIP_POLL_MS)
        }
    }

    fun refreshNow() {
        viewModelScope.launch { pollOnce() }
    }

    fun runCleanup() {
        viewModelScope.launch {
            _state.update { it.copy(busy = true, cleanupResult = null) }
            try {
                val summary = withContext(Dispatchers.IO) { client().runSystemCleanup() }
                _state.update { it.copy(busy = false, cleanupResult = summary) }
                pollOnce()
            } catch (e: Exception) {
                _state.update {
                    it.copy(busy = false, error = e.message ?: e.javaClass.simpleName)
                }
            }
        }
    }

    fun clearError() {
        _state.update { it.copy(error = "") }
    }

    private fun pollMs(): Long = if (_state.value.expanded) EXPANDED_POLL_MS else CHIP_POLL_MS

    private fun startPolling(intervalMs: Long) {
        stopPolling()
        pollJob = viewModelScope.launch {
            while (isActive) {
                pollOnce()
                delay(intervalMs)
            }
        }
    }

    private fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    private suspend fun pollOnce() {
        try {
            val appRssMb = currentAppRssMb()
            val resources = withContext(Dispatchers.IO) { client().getSystemResources() }
            _state.update {
                it.copy(resources = resources, appRssMb = appRssMb, error = "")
            }
        } catch (e: Exception) {
            _state.update { it.copy(error = e.message ?: e.javaClass.simpleName) }
        }
    }

    private fun client(): HermesApiClient {
        clientRef.get()?.let { return it }
        val runtime = HermesRuntimeManager.currentState()
        val baseUrl = runtime.baseUrl ?: throw IllegalStateException("Hermes runtime not ready")
        val client = HermesApiClient(
            baseUrl = baseUrl,
            apiKey = runtime.apiKey,
        )
        val previous = clientRef.getAndSet(client)
        if (previous != null && previous !== client) {
            // Runtime URL changed; drop the stale client silently.
            clientRef.set(client)
        }
        return client
    }

    private fun currentAppRssMb(): Double? = runCatching {
        val debugInfo = Debug.MemoryInfo()
        Debug.getMemoryInfo(debugInfo)
        debugInfo.totalPss / 1024.0
    }.getOrNull() ?: runCatching {
        // Fallback: rough process RSS from Runtime when PSS is unavailable in tests.
        (Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory()) / (1024.0 * 1024.0)
    }.getOrNull()

    companion object {
        const val CHIP_POLL_MS = 5_000L
        const val EXPANDED_POLL_MS = 2_000L

        /** Compact chip label, e.g. "RAM 412MB" — python+app combined when both known. */
        fun chipLabel(appRssMb: Double?, resources: SystemResources?): String {
            val python = resources?.python?.rssMb
            val parts = listOfNotNull(appRssMb, python)
            if (parts.isEmpty()) return "RAM --"
            val total = parts.sum()
            return "RAM " + formatMb(total)
        }

        fun formatMb(mb: Double): String = when {
            mb >= 1024 -> String.format("%.1fGB", mb / 1024.0)
            else -> "${mb.toInt()}MB"
        }

        /** Sheet row builder — hides null metrics entirely instead of showing fake values. */
        fun sheetRows(state: State): List<String> = buildList {
            val r = state.resources
            if (r == null) {
                add("Waiting for resource sample…")
                return@buildList
            }
            state.appRssMb?.let { add("App RAM ${formatMb(it)}") }
            r.python?.let { py ->
                val cpu = py.cpuPercent?.let { " · CPU %.0f%%".format(it) } ?: ""
                val threads = py.threads?.let { " · $it threads" } ?: ""
                add("Python RAM ${formatMb(py.rssMb ?: 0.0)}$cpu$threads")
            }
            r.localModel?.rssMb?.let { add("Local model RAM ${formatMb(it)}") }
            r.linuxMb?.let { add("Linux subsystem RAM ${formatMb(it)}") }
            r.gpuPercent?.let { add("GPU via LiteRT-LM · %.0f%%".format(it)) }
            r.npuPercent?.let { add("NPU · %.0f%%".format(it)) }
            if (r.gpuPercent == null && r.npuPercent == null) {
                add(r.note.ifBlank { "GPU/NPU not exposed by device" })
            }
        }
    }
}
