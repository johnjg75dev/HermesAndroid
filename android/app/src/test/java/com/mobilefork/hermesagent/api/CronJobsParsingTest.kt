package com.mobilefork.hermesagent.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CronJobsParsingTest {

    @Test
    fun parseCronJobsReadsNameScheduleAndPausedFlag() {
        val body = """
            {"jobs": [
              {"id": "job-1", "name": "Morning email", "prompt": "check email",
               "schedule_display": "every day 9am", "paused": false},
              {"id": "job-2", "name": null, "prompt": null,
               "schedule_display": null, "paused": true}
            ]}
        """.trimIndent()

        val jobs = parseCronJobs(body)

        assertEquals(2, jobs.size)
        assertEquals("job-1", jobs[0].id)
        assertEquals("Morning email", jobs[0].name)
        assertEquals("every day 9am", jobs[0].scheduleDisplay)
        assertTrue(!jobs[0].paused)
        assertEquals("Untitled job", jobs[1].name)
        assertEquals("manual", jobs[1].scheduleDisplay)
        assertTrue(jobs[1].paused)
    }

    @Test
    fun parseCronJobsSkipsUnknownIdsAndEmptyPayloads() {
        assertTrue(parseCronJobs("""{"jobs": []}""").isEmpty())
        assertTrue(parseCronJobs("{}").isEmpty())
        assertEquals(
            0,
            parseCronJobs("""{"jobs": [{"id": "unknown", "name": "x"}]}""").size,
        )
    }
}
