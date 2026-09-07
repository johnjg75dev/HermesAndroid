package com.mobilefork.hermesagent.ui.files

import android.app.Application
import androidx.compose.foundation.clickable
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
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.api.WorkspaceEntry
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class FilesUiState(
    val loading: Boolean = true,
    val currentPath: String = "",
    val entries: List<WorkspaceEntry> = emptyList(),
    val openFile: OpenFileUi? = null,
    val error: String = "",
)

data class OpenFileUi(
    val path: String,
    val content: String,
    val truncated: Boolean,
    val editing: Boolean = false,
)

class FilesViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(FilesUiState())
    val uiState: StateFlow<FilesUiState> = _uiState.asStateFlow()

    init {
        refresh("")
    }

    fun refresh(path: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(loading = true, error = "", openFile = null) }
            try {
                val listing = withContext(Dispatchers.IO) { client().listWorkspaceFiles(path) }
                _uiState.update {
                    it.copy(loading = false, currentPath = listing.path, entries = listing.entries)
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(loading = false, error = e.message ?: e.javaClass.simpleName) }
            }
        }
    }

    fun openDirectory(entry: WorkspaceEntry) {
        if (!entry.isDirectory) return
        val next = joinPath(_uiState.value.currentPath, entry.name)
        refresh(next)
    }

    fun navigateUp() {
        val current = _uiState.value.currentPath.trim('/')
        if (current.isBlank()) return
        refresh(current.substringBeforeLast('/', ""))
    }

    fun openFile(entry: WorkspaceEntry) {
        if (entry.isDirectory) {
            openDirectory(entry)
            return
        }
        val path = joinPath(_uiState.value.currentPath, entry.name)
        viewModelScope.launch {
            try {
                val (content, truncated) = withContext(Dispatchers.IO) {
                    client().readWorkspaceFile(path)
                }
                _uiState.update { it.copy(openFile = OpenFileUi(path = path, content = content, truncated = truncated)) }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = e.message ?: e.javaClass.simpleName) }
            }
        }
    }

    fun updateOpenContent(value: String) {
        _uiState.update { state ->
            state.openFile?.let { file -> state.copy(openFile = file.copy(content = value, editing = true)) }
                ?: state
        }
    }

    fun saveOpenFile() {
        val file = _uiState.value.openFile ?: return
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) { client().writeWorkspaceFile(file.path, file.content) }
                _uiState.update {
                    it.copy(openFile = file.copy(editing = false), error = "")
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(error = e.message ?: e.javaClass.simpleName) }
            }
        }
    }

    fun closeOpenFile() {
        _uiState.update { it.copy(openFile = null) }
    }

    private fun joinPath(base: String, name: String): String =
        if (base.isBlank()) name else "$base/$name"

    private fun client(): HermesApiClient {
        val runtime = HermesRuntimeManager.currentState()
        require(runtime.started) { "Waiting for Hermes runtime…" }
        val baseUrl = runtime.baseUrl ?: throw IllegalStateException("Runtime URL unavailable")
        return HermesApiClient(baseUrl = baseUrl, apiKey = runtime.apiKey)
    }
}

@Composable
fun FilesScreen(
    modifier: Modifier = Modifier,
    viewModel: FilesViewModel = viewModel(),
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
            Column(modifier = Modifier.weight(1f)) {
                Text("Workspace files", style = MaterialTheme.typography.headlineSmall)
                Text(
                    "workspace/" + uiState.currentPath,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Button(onClick = { viewModel.refresh(uiState.currentPath) }) {
                Text(if (uiState.loading) "…" else "Refresh")
            }
        }

        uiState.openFile?.let { file ->
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.surfaceVariant,
                shape = MaterialTheme.shapes.medium,
            ) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(file.path, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    androidx.compose.material3.OutlinedTextField(
                        value = file.content,
                        onValueChange = viewModel::updateOpenContent,
                        modifier = Modifier.fillMaxWidth(),
                        textStyle = MaterialTheme.typography.bodySmall,
                        minLines = 4,
                        maxLines = 12,
                    )
                    if (file.truncated) {
                        Text(
                            "Preview truncated at 200k characters.",
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = viewModel::saveOpenFile, enabled = file.editing) {
                            Text("Save")
                        }
                        OutlinedButton(onClick = viewModel::closeOpenFile) {
                            Text("Close")
                        }
                    }
                }
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

        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (uiState.currentPath.isNotBlank()) {
                item(key = "up") {
                    Text(
                        "↰ ..",
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable(onClick = viewModel::navigateUp)
                            .padding(vertical = 8.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            items(uiState.entries, key = { it.name }) { entry ->
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = MaterialTheme.shapes.medium,
                    onClick = { if (entry.isDirectory) viewModel.openDirectory(entry) else viewModel.openFile(entry) },
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            (if (entry.isDirectory) "▸ " else "") + entry.name,
                            modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.bodyMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (!entry.isDirectory) {
                            Text(
                                formatSize(entry.sizeBytes),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

private fun formatSize(bytes: Long): String = when {
    bytes >= 1 shl 20 -> "${"%.1f".format(bytes / 1048576.0)}MB"
    bytes >= 1 shl 10 -> "${bytes / 1024}KB"
    else -> "${bytes}B"
}
