package com.mobilefork.hermesagent.ui.insights

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.api.InsightsSnapshot
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class InsightsUiState(
    val loading: Boolean = true,
    val snapshot: InsightsSnapshot? = null,
    val error: String = "",
)

class InsightsViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(InsightsUiState())
    val uiState: StateFlow<InsightsUiState> = _uiState.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(loading = true, error = "") }
            try {
                val snapshot = withContext(Dispatchers.IO) { client().getInsights() }
                _uiState.update { it.copy(loading = false, snapshot = snapshot) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(loading = false, error = e.message ?: e.javaClass.simpleName)
                }
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

@Composable
fun InsightsScreen(
    modifier: Modifier = Modifier,
    viewModel: InsightsViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Insights", style = MaterialTheme.typography.headlineSmall)
            Button(onClick = viewModel::refresh) {
                Text(if (uiState.loading) "Refreshing…" else "Refresh")
            }
        }
        val snapshot = uiState.snapshot
        if (uiState.error.isNotBlank()) {
            InsightCard { Text(uiState.error, style = MaterialTheme.typography.bodySmall) }
        } else if (snapshot == null || !snapshot.available) {
            InsightCard {
                Text(
                    "No usage data yet. Runs, tokens, and cost appear after your first chats.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    InsightCard {
                        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("All time", style = MaterialTheme.typography.titleMedium)
                            StatRow("Runs", formatLong(snapshot.runs))
                            StatRow("Messages", formatLong(snapshot.messages))
                            StatRow("Tool calls", formatLong(snapshot.toolCalls))
                            StatRow("Tokens in / out", "${formatLong(snapshot.inputTokens)} / ${formatLong(snapshot.outputTokens)}")
                            if (snapshot.cacheReadTokens > 0) {
                                StatRow("Cache reads", formatLong(snapshot.cacheReadTokens))
                            }
                            if (snapshot.reasoningTokens > 0) {
                                StatRow("Reasoning tokens", formatLong(snapshot.reasoningTokens))
                            }
                            StatRow("Cost", "$${"%.2f".format(snapshot.costUsd)}")
                        }
                    }
                }
                item {
                    InsightCard {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("Last 14 days", style = MaterialTheme.typography.titleMedium)
                            DailyBars(snapshot.daily)
                        }
                    }
                }
                if (snapshot.models.isNotEmpty()) {
                    item {
                        InsightCard {
                            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("By model", style = MaterialTheme.typography.titleMedium)
                                snapshot.models.forEach { model ->
                                    StatRow(
                                        model.model,
                                        "${formatLong(model.runs)} runs · ${formatLong(model.tokens)} tok · $${"%.2f".format(model.costUsd)}",
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun InsightCard(content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.large,
    ) {
        Column(modifier = Modifier.padding(16.dp), content = content)
    }
}

@Composable
private fun StatRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
        )
    }
}

/** Simple bar strip — height proportional to the max daily token total. */
@Composable
private fun DailyBars(entries: List<com.mobilefork.hermesagent.api.InsightsDailyEntry>) {
    val maxTokens = entries.maxOfOrNull { it.tokens }?.coerceAtLeast(1L) ?: 1L
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(72.dp),
        horizontalArrangement = Arrangement.spacedBy(3.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        entries.forEach { entry ->
            val fraction = entry.tokens.toFloat() / maxTokens.toFloat()
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Bottom,
            ) {
                Box(
                    modifier = Modifier
                        .width(14.dp)
                        .height((10 + 62 * fraction).dp)
                        .background(
                            color = if (entry.tokens > 0) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.surfaceVariant
                            },
                            shape = MaterialTheme.shapes.small,
                        ),
                )
            }
        }
    }
    Text(
        "runs/day · peak ${formatLong(maxTokens)} tokens",
        style = MaterialTheme.typography.labelSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

private fun formatLong(value: Long): String = java.text.DecimalFormat("#,###").format(value)
