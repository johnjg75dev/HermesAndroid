package com.mobilefork.hermesagent.profile

import android.content.Context
import android.content.SharedPreferences
import com.mobilefork.hermesagent.core.error.HermesError
import com.mobilefork.hermesagent.core.error.HermesErrorCode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

class ProfileManager {

    private val PROFILES_DIR_NAME = "profiles"
    private val ACTIVE_PROFILE_FILE = ".active"
    private val DEFAULT_PROFILE = "default"

    fun getProfilesRoot(context: Context): File {
        val hermesHome = File(context.filesDir, ".hermes")
        return File(hermesHome, PROFILES_DIR_NAME)
    }

    fun getActiveProfileName(context: Context): String {
        val profilesRoot = getProfilesRoot(context)
        val activeFile = File(profilesRoot, ACTIVE_PROFILE_FILE)
        return if (activeFile.exists()) {
            try {
                activeFile.readText().trim().takeIf { it.isNotBlank() } ?: DEFAULT_PROFILE
            } catch (e: Exception) {
                DEFAULT_PROFILE
            }
        } else {
            DEFAULT_PROFILE
        }
    }

    suspend fun setActiveProfile(context: Context, name: String): Result<Unit> = withContext(Dispatchers.IO) {
        val profilesRoot = getProfilesRoot(context)
        val profileDir = File(profilesRoot, name)
        if (!profileDir.exists()) {
            return@withContext Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_NOT_FOUND, "Profile '$name' does not exist"))
        }

        val activeFile = File(profilesRoot, ACTIVE_PROFILE_FILE)
        try {
            activeFile.writeText(name)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Failed to switch profile: ${e.message}", cause = e))
        }
    }

    suspend fun createProfile(context: Context, name: String): Result<File> = withContext(Dispatchers.IO) {
        if (name.isBlank() || !Regex("^[a-zA-Z0-9_-]+$").matches(name)) {
            return@withContext Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Invalid profile name"))
        }

        val profilesRoot = getProfilesRoot(context)
        val profileDir = File(profilesRoot, name)
        if (profileDir.exists()) {
            return@withContext Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Profile '$name' already exists"))
        }

        try {
            // Create profile directory structure
            profileDir.mkdirs()
            File(profileDir, "hermes-home").mkdirs()
            File(profileDir, "hermes-home/logs").mkdirs()
            File(profileDir, "hermes-home/sessions").mkdirs()
            File(profileDir, "hermes-home/skills").mkdirs()
            File(profileDir, "hermes-home/downloads").mkdirs()
            File(profileDir, "hermes-home/workspace").mkdirs()

            Result.success(profileDir)
        } catch (e: Exception) {
            Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Failed to create profile: ${e.message}", cause = e))
        }
    }

    suspend fun deleteProfile(context: Context, name: String): Result<Unit> = withContext(Dispatchers.IO) {
        if (name == DEFAULT_PROFILE) {
            return@withContext Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Cannot delete default profile"))
        }

        val activeName = getActiveProfileName(context)
        if (name == activeName) {
            return@withContext Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Cannot delete active profile"))
        }

        val profilesRoot = getProfilesRoot(context)
        val profileDir = File(profilesRoot, name)
        if (!profileDir.exists()) {
            return@withContext Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_NOT_FOUND, "Profile '$name' does not exist"))
        }

        try {
            deleteRecursively(profileDir)
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(HermesError.fromCode(HermesErrorCode.PROFILE_SWITCH_FAILED, "Failed to delete profile: ${e.message}", cause = e))
        }
    }

    suspend fun listProfiles(context: Context): Result<List<ProfileInfo>> = withContext(Dispatchers.IO) {
        val profilesRoot = getProfilesRoot(context)
        if (!profilesRoot.exists()) {
            return@withContext Result.success(emptyList())
        }

        val activeName = getActiveProfileName(context)
        val profiles = profilesRoot.listFiles()?.filter { it.isDirectory && it.name != ACTIVE_PROFILE_FILE }
            ?.map { dir ->
                ProfileInfo(
                    name = dir.name,
                    active = dir.name == activeName,
                    path = dir.absolutePath,
                    hermesHome = File(dir, "hermes-home").absolutePath,
                )
            } ?: emptyList()

        Result.success(profiles.toList())
    }

    fun getProfileHermesHome(context: Context, name: String): File {
        val profilesRoot = getProfilesRoot(context)
        return File(profilesRoot, name).apply { mkdirs() }
            .let { File(it, "hermes-home").apply { mkdirs() } }
    }

    private fun deleteRecursively(file: File) {
        if (file.isDirectory) {
            file.listFiles()?.forEach { deleteRecursively(it) }
        }
        file.delete()
    }

    data class ProfileInfo(
        val name: String,
        val active: Boolean,
        val path: String,
        val hermesHome: String,
    )
}