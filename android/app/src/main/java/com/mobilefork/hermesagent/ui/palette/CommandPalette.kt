package com.mobilefork.hermesagent.ui.palette

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.backend.HermesRuntimeManager

/** One searchable palette entry (M05). */
data class PaletteItem(
    val kind: String,
    val title: String,
    val subtitle: String,
    val keywords: String = "",
)

/**
 * M05 command palette: fuzzy-filtered index across slash commands,
 * navigation sections, and installed skills (best-effort live fetch).
 */
@Composable
fun CommandPaletteDialog(
    baseItems: List<PaletteItem>,
    onDismiss: () -> Unit,
    onPick: (PaletteItem) -> Unit,
) {
    var query by rememberSaveable { mutableStateOf("") }
    val skillItems by produceState<List<PaletteItem>>(initialValue = emptyList(), key1 = Unit) {
        value = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            runCatching {
            val runtime = HermesRuntimeManager.currentState()
            if (!runtime.started || runtime.baseUrl.isNullOrBlank()) {
                return@runCatching emptyList()
            }
            val client = HermesApiClient(baseUrl = runtime.baseUrl, apiKey = runtime.apiKey)
            val body = client.getManageJson("/v1/manage/skills")
            val rows = org.json.JSONObject(body).optJSONArray("skills")
                ?: org.json.JSONArray()
            (0 until rows.length()).mapNotNull { i ->
                val row = rows.optJSONObject(i) ?: return@mapNotNull null
                val name = row.optString("name", "").ifBlank { return@mapNotNull null }
                PaletteItem(
                    kind = "skill",
                    title = "skill: $name",
                    subtitle = row.optString("description", ""),
                    keywords = name,
                )
            }
            }.getOrDefault(emptyList())
        }
    }

    val allItems = baseItems + skillItems
    val needle = query.trim().lowercase()
    val filtered = if (needle.isBlank()) {
        allItems.take(12)
    } else {
        allItems.filter { item ->
            item.title.lowercase().contains(needle) ||
                item.keywords.lowercase().contains(needle) ||
                item.subtitle.lowercase().contains(needle)
        }.take(24)
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Search commands, screens, skills…") },
                    singleLine = true,
                )
                if (filtered.isEmpty()) {
                    Text(
                        "No matches",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 8.dp),
                    )
                }
                LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    items(filtered, key = { "${it.kind}:${it.title}" }) { item ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable(onClick = { onPick(item) })
                                .padding(vertical = 6.dp, horizontal = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(item.title, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
                                if (item.subtitle.isNotBlank()) {
                                    Text(
                                        item.subtitle,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                    )
                                }
                            }
                            Text(
                                item.kind,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }
        }
    }
}
