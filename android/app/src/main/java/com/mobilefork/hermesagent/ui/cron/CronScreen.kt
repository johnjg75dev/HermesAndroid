package com.mobilefork.hermesagent.ui.cron

import android.app.Application
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.mobilefork.hermesagent.api.CronJobSummary
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class CronUiState(
    val loading: Boolean = true,
    val jobs: List<CronJobSummary> = emptyList(),
    val error: String = "",
    val statusMessage: String = "",
)

class CronViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(CronUiState())
    val uiState: StateFlow<CronUiState> = _uiState.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(loading = true, error = "") }
            try {
                val jobs = withContext(Dispatchers.IO) { client().listCronJobs() }
                _uiState.update { it.copy(loading = false, jobs = jobs, statusMessage = "") }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(
                        loading = false,
                        error = e.message ?: e.javaClass.simpleName,
                    )
                }
            }
        }
    }

    fun togglePause(job: CronJobSummary) {
        mutate(job.id, if (job.paused) "resumed" else "paused") { client ->
            if (job.paused) client.resumeCronJob(job.id) else client.pauseCronJob(job.id)
        }
    }

    fun deleteJob(jobId: String) {
        mutate(jobId, "removed") { client -> client.deleteCronJob(jobId) }
    }

    private fun mutate(jobId: String, actionLabel: String, block: (HermesApiClient) -> Boolean) {
        viewModelScope.launch {
            _uiState.update { it.copy(loading = true, error = "") }
            try {
                withContext(Dispatchers.IO) { block(client()) }
                val jobs = withContext(Dispatchers.IO) { client().listCronJobs() }
                _uiState.update {
                    it.copy(
                        loading = false,
                        jobs = jobs,
                        statusMessage = "Job $actionLabel",
                    )
                }
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
fun CronScreen(
    modifier: Modifier = Modifier,
    viewModel: CronViewModel = viewModel(),
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
            Text("Scheduled tasks", style = MaterialTheme.typography.headlineSmall)
            Button(onClick = viewModel::refresh) {
                Text(if (uiState.loading) "Refreshing…" else "Refresh")
            }
        }
        if (uiState.error.isNotBlank()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.errorContainer,
                shape = MaterialTheme.shapes.medium,
            ) {
                Text(
                    uiState.error,
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        if (!uiState.statusMessage.isBlank()) {
            Text(
                uiState.statusMessage,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        if (uiState.jobs.isEmpty() && !uiState.loading && uiState.error.isBlank()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = MaterialTheme.shapes.large,
            ) {
                Text(
                    "No scheduled tasks yet. Ask Hermes to schedule one, e.g. “every morning at 9, check my email”.",
                    modifier = Modifier.padding(16.dp),
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(uiState.jobs, key = { it.id }) { job ->
                    CronJobCard(
                        job = job,
                        onTogglePause = { viewModel.togglePause(job) },
                        onDelete = { viewModel.deleteJob(job.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun CronJobCard(
    job: CronJobSummary,
    onTogglePause: () -> Unit,
    onDelete: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.large,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    job.name,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Surface(
                    shape = MaterialTheme.shapes.small,
                    color = if (job.paused) {
                        MaterialTheme.colorScheme.errorContainer
                    } else {
                        MaterialTheme.colorScheme.primaryContainer
                    },
                ) {
                    Text(
                        if (job.paused) "Paused" else "Active",
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
            Text(
                job.scheduleDisplay,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            if (job.prompt.isNotBlank()) {
                Text(
                    job.prompt,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                OutlinedButton(onClick = onTogglePause) {
                    Text(if (job.paused) "Resume" else "Pause")
                }
                TextButton(onClick = onDelete) {
                    Text("Delete", color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}
