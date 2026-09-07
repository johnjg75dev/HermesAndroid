package com.mobilefork.hermesagent.ui.boot

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class BootPhaseUi(
    val name: String,
    val fatal: Boolean,
    val status: String,
    val error: String? = null,
    val durationMs: Double = 0.0,
)

data class BootUiState(
    val status: String = "Opening Hermes…",
    val ready: Boolean = false,
    val probeResult: String = "",
    val baseUrl: String = "",
    val error: String = "",
    /** M01 boot checklist — real per-phase outcomes from the Python runtime. */
    val phases: List<BootPhaseUi> = emptyList(),
)

class BootViewModel(application: Application) : AndroidViewModel(application) {
    private val _uiState = MutableStateFlow(BootUiState())
    val uiState: StateFlow<BootUiState> = _uiState.asStateFlow()

    fun refresh() {
        _uiState.value = _uiState.value.copy(status = "Starting Hermes runtime…", error = "")
        viewModelScope.launch(Dispatchers.IO) {
            // Idempotent + synchronized: safe to race other callers.
            val runtime = HermesRuntimeManager.ensureStarted(getApplication())
            _uiState.value = BootUiState(
                status = when {
                    runtime.started -> "Hermes shell ready"
                    !runtime.error.isNullOrBlank() -> "Hermes runtime unavailable"
                    else -> "Starting Hermes runtime…"
                },
                ready = runtime.started && runtime.error == null,
                probeResult = runtime.probeResult.orEmpty(),
                baseUrl = runtime.baseUrl.orEmpty(),
                error = runtime.error.orEmpty(),
                phases = runtime.phases.map { phase ->
                    BootPhaseUi(
                        name = phase.name,
                        fatal = phase.fatal,
                        status = phase.status,
                        error = phase.error,
                        durationMs = phase.durationMs,
                    )
                },
            )
        }
    }
}
