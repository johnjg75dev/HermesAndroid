package com.mobilefork.hermesagent.ui.resources

import com.mobilefork.hermesagent.api.parseSystemResources
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ResourceGaugeViewModelTest {

    @Test
    fun parseSystemResources_readsPythonSampleAndHidesNulls() {
        val body = """
            {
              "python": {"pid": 42, "rss_mb": 318.4, "threads": 12, "cpu_percent": null},
              "app": null,
              "local_model": null,
              "linux": 96.2,
              "gpu_percent": null,
              "npu_percent": null,
              "note": "GPU/NPU appear only when a backend self-reports."
            }
        """.trimIndent()

        val resources = parseSystemResources(body)

        assertEquals(318.4, resources.python?.rssMb!!, 0.001)
        assertEquals(12, resources.python?.threads)
        assertNull(resources.python?.cpuPercent)
        assertNull(resources.app)
        assertEquals(96.2, resources.linuxMb!!, 0.001)
        assertNull(resources.gpuPercent)
        assertNull(resources.npuPercent)
    }

    @Test
    fun parseSystemResources_toleratesEmptyPayload() {
        val resources = parseSystemResources(JSONObject().toString())
        assertNull(resources.python)
        assertNull(resources.app)
        assertNull(resources.linuxMb)
        assertEquals("", resources.note)
    }

    @Test
    fun chipLabelCombinesAppAndPythonAndFormatsGb() {
        val resources = parseSystemResources(
            """{"python": {"rss_mb": 512.0, "cpu_percent": null, "threads": null}}""",
        )
        assertEquals("RAM 924MB", ResourceGaugeViewModel.chipLabel(appRssMb = 412.0, resources = resources))
        assertEquals("RAM --", ResourceGaugeViewModel.chipLabel(appRssMb = null, resources = null))
    }

    @Test
    fun formatMbUsesMbBelowOneGb() {
        assertEquals("999MB", ResourceGaugeViewModel.formatMb(999.4))
        assertEquals("1.1GB", ResourceGaugeViewModel.formatMb(1126.0))
    }

    @Test
    fun sheetRowsHideUnreportedMetricsButExplainMissingAccelerators() {
        val state = ResourceGaugeViewModel.State(
            appRssMb = 200.0,
            resources = parseSystemResources(
                """
                {
                  "python": {"pid": 1, "rss_mb": 300.0, "threads": 8, "cpu_percent": 22.5},
                  "app": null,
                  "linux": null,
                  "gpu_percent": null,
                  "npu_percent": null,
                  "note": "not exposed"
                }
                """.trimIndent(),
            ),
        )

        val rows = ResourceGaugeViewModel.sheetRows(state)

        assertTrue(rows.any { it.startsWith("App RAM") })
        assertTrue(rows.any { it.contains("Python RAM") && it.contains("CPU 23%") && it.contains("8 threads") })
        assertTrue(rows.none { it.startsWith("Linux") })
        assertTrue(rows.any { it == "not exposed" })
    }
}
