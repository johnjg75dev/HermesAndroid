package com.mobilefork.hermesagent.core.error

enum class HermesErrorCode(
    val code: String,
    val retryable: Boolean = false,
    val userMessage: String? = null,
) {
    // Bridge / API errors
    UNSUPPORTED_BRIDGE_VERSION("UNSUPPORTED_BRIDGE_VERSION", false, "Bridge version mismatch. Please update the Hermes app."),
    BRIDGE_CONNECTION_FAILED("BRIDGE_CONNECTION_FAILED", true, "Failed to connect to the Hermes runtime."),
    BRIDGE_HANDSHAKE_FAILED("BRIDGE_HANDSHAKE_FAILED", false, "Bridge handshake failed. Please restart the app."),

    // Profile errors
    PROFILE_NOT_FOUND("PROFILE_NOT_FOUND", false, "The requested profile does not exist."),
    PROFILE_SWITCH_FAILED("PROFILE_SWITCH_FAILED", false, "Failed to switch profiles. Please try again."),
    PROFILE_CORRUPTED("PROFILE_CORRUPTED", false, "Profile data is corrupted. Please create a new profile."),

    // Config errors
    CONFIG_VALIDATION_FAILED("CONFIG_VALIDATION_FAILED", false, "Configuration validation failed."),
    CONFIG_MIGRATION_FAILED("CONFIG_MIGRATION_FAILED", false, "Failed to migrate configuration."),

    // Runtime errors
    RUNTIME_NOT_STARTED("RUNTIME_NOT_STARTED", true, "Hermes runtime is not started."),
    RUNTIME_ALREADY_RUNNING("RUNTIME_ALREADY_RUNNING", false, "Hermes runtime is already running."),
    RUNTIME_START_FAILED("RUNTIME_START_FAILED", true, "Failed to start Hermes runtime."),
    RUNTIME_STOP_FAILED("RUNTIME_STOP_FAILED", true, "Failed to stop Hermes runtime."),
    RUNTIME_CRASHED("RUNTIME_CRASHED", true, "Hermes runtime crashed. Restarting..."),
    BOOT_PHASE_FAILED("BOOT_PHASE_FAILED", false, "Boot phase failed."),
    BOOT_FATAL_PHASE_FAILED("BOOT_FATAL_PHASE_FAILED", false, "Fatal boot phase failed. Cannot continue."),

    // Device facade errors
    DEVICE_UNAVAILABLE("DEVICE_UNAVAILABLE", true, "Device capability is currently unavailable."),
    PERMISSION_MISSING("PERMISSION_MISSING", false, "Required Android permission is not granted."),
    FACADE_TIMEOUT("FACADE_TIMEOUT", true, "Device operation timed out."),
    FACADE_CANCELLED("FACADE_CANCELLED", false, "Device operation was cancelled."),
    CONSENT_DENIED("CONSENT_DENIED", false, "User denied consent for this operation."),

    // Linux subsystem errors
    LINUX_SUBSYSTEM_UNAVAILABLE("LINUX_SUBSYSTEM_UNAVAILABLE", true, "Linux subsystem is not available."),
    LINUX_SUBSYSTEM_DEGRADED("LINUX_SUBSYSTEM_DEGRADED", true, "Linux subsystem is running in degraded mode."),
    LINUX_PROOT_NOT_FOUND("LINUX_PROOT_NOT_FOUND", false, "proot-distro not found. Cannot start Linux userland."),
    LINUX_TERMUX_NOT_FOUND("LINUX_TERMUX_NOT_FOUND", false, "Termux not found."),
    LINUX_PACKAGE_INSTALL_FAILED("LINUX_PACKAGE_INSTALL_FAILED", true, "Failed to install package in Linux subsystem."),

    // Resource errors
    RESOURCE_GAUGE_FAILED("RESOURCE_GAUGE_FAILED", true, "Failed to read resource metrics."),
    CLEANUP_FAILED("CLEANUP_FAILED", true, "Resource cleanup partially failed."),

    // Memory provider errors
    MEMORY_PROVIDER_UNAVAILABLE("MEMORY_PROVIDER_UNAVAILABLE", true, "Memory provider is not available."),
    MEMORY_PROVIDER_SETUP_FAILED("MEMORY_PROVIDER_SETUP_FAILED", false, "Failed to set up memory provider."),

    // MCP errors
    MCP_SERVER_NOT_FOUND("MCP_SERVER_NOT_FOUND", false, "MCP server not found."),
    MCP_SERVER_START_FAILED("MCP_SERVER_START_FAILED", true, "Failed to start MCP server."),

    // Session errors
    SESSION_NOT_FOUND("SESSION_NOT_FOUND", false, "Session not found."),
    SESSION_DB_ERROR("SESSION_DB_ERROR", true, "Session database error."),

    // Generic / catch-all
    INTERNAL_ERROR("INTERNAL_ERROR", true, "An internal error occurred."),
    UNKNOWN_ERROR("UNKNOWN_ERROR", false, "An unknown error occurred.")
    ;
    companion object {
        fun fromCode(code: String): HermesErrorCode {
            return values().firstOrNull { it.code == code } ?: UNKNOWN_ERROR
        }

        fun allCodes(): List<String> = values().map { it.code }
    }
}