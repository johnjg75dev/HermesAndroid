package com.mobilefork.hermesagent.device.facade.impl

import com.mobilefork.hermesagent.device.facade.*

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.Result
import kotlinx.coroutines.CompletableDeferred

class SensorsFacadeImpl(private val context: Context) : DeviceFacade {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    override suspend fun sensorsList(runId: String?): Result<List<SensorInfo>> {
        return try {
            val sensors = sensorManager.getSensorList(Sensor.TYPE_ALL)
            val infos = sensors.map { s ->
                SensorInfo(
                    name = s.name,
                    type = s.type,
                    vendor = s.vendor,
                    maxRange = s.maximumRange,
                    resolution = s.resolution,
                    power = s.power,
                )
            }
            Result.success(infos)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Sensors list failed: ${e.message}", cause = e))
        }
    }

    override suspend fun sensorsRead(
        sensorType: String,
        runId: String?,
    ): Result<SensorReading> {
        return try {
            val type = sensorType.toIntOrNull() ?: return Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Invalid sensor type"))
            val sensor = sensorManager.getDefaultSensor(type)
            if (sensor == null) {
                return Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Sensor not available"))
            }

            // For one-shot reading, we'd need to register a listener
            // This is a simplified version
            Result.success(SensorReading(
                sensorType = sensorType,
                values = floatArrayOf(0f),
                timestamp = System.currentTimeMillis(),
                accuracy = SensorManager.SENSOR_STATUS_ACCURACY_HIGH,
            ))
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Sensor read failed: ${e.message}", cause = e))
        }
    }

    override suspend fun locationGet(runId: String?): Result<LocationInfo> {
        return try {
            val deferred = CompletableDeferred<LocationInfo>()
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    deferred.complete(LocationInfo(
                        latitude = location.latitude,
                        longitude = location.longitude,
                        altitude = location.altitude.takeIf { it > 0 },
                        accuracy = location.accuracy,
                        timestamp = location.time,
                    ))
                    locationManager.removeUpdates(this)
                }
                override fun onStatusChanged(provider: String, status: Int, extras: Bundle?) {}
                override fun onProviderEnabled(provider: String) {}
                override fun onProviderDisabled(provider: String) {}
            }

            val provider = if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                LocationManager.GPS_PROVIDER
            } else {
                LocationManager.NETWORK_PROVIDER
            }

            locationManager.requestSingleUpdate(provider, listener, null)
            val result = deferred.await()
            Result.success(result)
        } catch (e: Exception) {
            Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Location get failed: ${e.message}", cause = e))
        }
    }

    // Delegate other methods
    override suspend fun terminalExec(command: String, timeoutSeconds: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalSpawn(command: String, cwd: String?, env: Map<String, String>?, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalKill(pid: Int, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun terminalList(runId: String?): Result<List<TerminalSession>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use terminal facade"))
    override suspend fun fileRead(path: String, maxChars: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileWrite(path: String, content: String, append: Boolean, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileList(path: String, recursive: Boolean, runId: String?): Result<List<FileEntry>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileDelete(path: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun fileSearch(path: String, pattern: String, runId: String?): Result<List<FileEntry>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use file facade"))
    override suspend fun systemInfo(runId: String?): Result<SystemInfo> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use system facade"))
    override suspend fun systemAction(action: String, args: Map<String, Any>?, runId: String?): Result<Any> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use system facade"))
    override suspend fun accessibilitySnapshot(limit: Int, runId: String?): Result<AccessibilitySnapshot> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use accessibility facade"))
    override suspend fun accessibilityAction(action: String, vararg args: Pair<String, Any>): Result<Any> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use accessibility facade"))
    override suspend fun projectionStart(runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use projection facade"))
    override suspend fun projectionStop(runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use projection facade"))
    override suspend fun projectionScreenshot(runId: String?): Result<ByteArray> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use projection facade"))
    override suspend fun calendarQuery(query: String, runId: String?): Result<List<CalendarEvent>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use calendar facade"))
    override suspend fun logcatRead(filterSpec: String, maxLines: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use logcat facade"))
    override suspend fun notificationsList(limit: Int, runId: String?): Result<List<NotificationInfo>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use notifications facade"))
    override suspend fun clipboardGet(runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use clipboard facade"))
    override suspend fun clipboardSet(content: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use clipboard facade"))
    override suspend fun shareSend(content: String, mimeType: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use share facade"))
    override suspend fun ttsSpeak(text: String, language: String?, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use tts facade"))
    override suspend fun sttListen(language: String?, timeoutSeconds: Int, runId: String?): Result<String> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use stt facade"))
    override suspend fun notificationPost(title: String, body: String, channel: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use notifications post facade"))
    override suspend fun appsList(runId: String?): Result<List<AppInfo>> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use apps facade"))
    override suspend fun appsLaunch(packageName: String, runId: String?): Result<Unit> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use apps facade"))
    override suspend fun resourcesGet(runId: String?): Result<ResourceUsage> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use resources facade"))
    override suspend fun cleanupRun(components: List<String>?, runId: String?): Result<CleanupResult> = Result.failure(HermesError(HermesErrorCode.DEVICE_UNAVAILABLE, "Use cleanup facade"))
}