package com.mobilefork.hermesagent.ui.developer

import android.app.Application
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class DeveloperUiState(
    val loading: Boolean = false,
    val source: String = "agent",
    val level: String = "INFO",
    val lines: List<String> = emptyList(),
    val error: String = "",
)

class DeveloperViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(DeveloperUiState())
    val uiState: StateFlow<DeveloperUiState> = _uiState.asStateFlow()

    init {
        refresh()
    }

    fun setSource(source: String) {
        _uiState.update { it.copy(source = source) }
        refresh()
    }

    fun setLevel(level: String) {
        _uiState.update { it.copy(level = level) }
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val state = _uiState.value
            _uiState.update { it.copy(loading = true, error = "") }
            try {
                val client = withContext(Dispatchers.IO) { client() }
                val body = withContext(Dispatchers.IO) {
                    client.getManageJson(
                        "/v1/manage/system/logs?source=${state.source}&level=${state.level}&tail=400",
                    )
                }
                val json = org.json.JSONObject(body)
                val rows = json.optJSONArray("lines") ?: org.json.JSONArray()
                val lines = (0 until rows.length()).map { rows.optString(it) }
                _uiState.update { it.copy(loading = false, lines = lines) }
            } catch (e: Exception) {
                _uiState.update { it.copy(loading = false, error = e.message ?: e.javaClass.simpleName) }
            }
        }
    }

    private fun client(): HermesApiClient {
        val runtime = HermesRuntimeManager.currentState()
        require(runtime.started) { "Waiting for Hermes runtime…" }
        val baseUrl = runtime.baseUrl ?: throw IllegalStateException("Runtime URL unavailable")
        return HermesApiClient(baseUrl = baseUrl, apiKey = runtime.apiKey)
    }
}

private val SOURCES = listOf("agent", "errors", "gateway")
private val LEVELS = listOf("INFO", "WARNING", "ERROR")

@Composable
fun DeveloperScreen(
    modifier: Modifier = Modifier,
    viewModel: DeveloperViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Developer", style = MaterialTheme.typography.headlineSmall)
            Button(onClick = viewModel::refresh) {
                Text(if (uiState.loading) "…" else "Refresh")
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SOURCES.forEach { source ->
                FilterChip(
                    selected = uiState.source == source,
                    onClick = { viewModel.setSource(source) },
                    label = { Text(source) },
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            LEVELS.forEach { level ->
                FilterChip(
                    selected = uiState.level == level,
                    onClick = { viewModel.setLevel(level) },
                    label = { Text(level) },
                )
            }
        }
        if (uiState.error.isNotBlank()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.errorContainer,
                shape = MaterialTheme.shapes.medium,
            ) {
                Text(uiState.error, modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall)
            }
        }
        if (uiState.lines.isEmpty() && !uiState.loading && uiState.error.isBlank()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = MaterialTheme.shapes.large,
            ) {
                Text(
                    "No ${uiState.source} log lines at ${uiState.level}.",
                    modifier = Modifier.padding(16.dp),
                )
            }
        } else {
            Surface(
                modifier = Modifier.fillMaxSize(),
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = MaterialTheme.shapes.medium,
            ) {
                LazyColumn(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    items(uiState.lines) { line ->
                        Text(
                            line,
                            style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        )
                    }
                }
            }
        }
    }
}
