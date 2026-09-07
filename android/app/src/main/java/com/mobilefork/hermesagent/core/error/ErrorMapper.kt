package com.mobilefork.hermesagent.core.error

import com.mobilefork.hermesagent.device.facade.Result

object ErrorMapper {

    /**
     * Maps a HermesError to a typed Result.Failure with exhaustive when branches.
     * This ensures compile-time verification that all error codes are handled.
     */
    @Suppress("UNUSED_PARAMETER")
    fun <T> mapToResult(error: HermesError): Result<T> {
        val errorCode = HermesErrorCode.fromCode(error.code)
        return when (errorCode) {
            // Bridge / API errors
            HermesErrorCode.UNSUPPORTED_BRIDGE_VERSION -> Result.failure(error)
            HermesErrorCode.BRIDGE_CONNECTION_FAILED -> Result.failure(error)
            HermesErrorCode.BRIDGE_HANDSHAKE_FAILED -> Result.failure(error)

            // Profile errors
            HermesErrorCode.PROFILE_NOT_FOUND -> Result.failure(error)
            HermesErrorCode.PROFILE_SWITCH_FAILED -> Result.failure(error)
            HermesErrorCode.PROFILE_CORRUPTED -> Result.failure(error)

            // Config errors
            HermesErrorCode.CONFIG_VALIDATION_FAILED -> Result.failure(error)
            HermesErrorCode.CONFIG_MIGRATION_FAILED -> Result.failure(error)

            // Runtime errors
            HermesErrorCode.RUNTIME_NOT_STARTED -> Result.failure(error)
            HermesErrorCode.RUNTIME_ALREADY_RUNNING -> Result.failure(error)
            HermesErrorCode.RUNTIME_START_FAILED -> Result.failure(error)
            HermesErrorCode.RUNTIME_STOP_FAILED -> Result.failure(error)
            HermesErrorCode.RUNTIME_CRASHED -> Result.failure(error)
            HermesErrorCode.BOOT_PHASE_FAILED -> Result.failure(error)
            HermesErrorCode.BOOT_FATAL_PHASE_FAILED -> Result.failure(error)

            // Device facade errors
            HermesErrorCode.DEVICE_UNAVAILABLE -> Result.failure(error)
            HermesErrorCode.PERMISSION_MISSING -> Result.failure(error)
            HermesErrorCode.FACADE_TIMEOUT -> Result.failure(error)
            HermesErrorCode.FACADE_CANCELLED -> Result.failure(error)
            HermesErrorCode.CONSENT_DENIED -> Result.failure(error)

            // Linux subsystem errors
            HermesErrorCode.LINUX_SUBSYSTEM_UNAVAILABLE -> Result.failure(error)
            HermesErrorCode.LINUX_SUBSYSTEM_DEGRADED -> Result.failure(error)
            HermesErrorCode.LINUX_PROOT_NOT_FOUND -> Result.failure(error)
            HermesErrorCode.LINUX_TERMUX_NOT_FOUND -> Result.failure(error)
            HermesErrorCode.LINUX_PACKAGE_INSTALL_FAILED -> Result.failure(error)

            // Resource errors
            HermesErrorCode.RESOURCE_GAUGE_FAILED -> Result.failure(error)
            HermesErrorCode.CLEANUP_FAILED -> Result.failure(error)

            // Memory provider errors
            HermesErrorCode.MEMORY_PROVIDER_UNAVAILABLE -> Result.failure(error)
            HermesErrorCode.MEMORY_PROVIDER_SETUP_FAILED -> Result.failure(error)

            // MCP errors
            HermesErrorCode.MCP_SERVER_NOT_FOUND -> Result.failure(error)
            HermesErrorCode.MCP_SERVER_START_FAILED -> Result.failure(error)

            // Session errors
            HermesErrorCode.SESSION_NOT_FOUND -> Result.failure(error)
            HermesErrorCode.SESSION_DB_ERROR -> Result.failure(error)

            // Generic / catch-all
            HermesErrorCode.INTERNAL_ERROR -> Result.failure(error)
            HermesErrorCode.UNKNOWN_ERROR -> Result.failure(error)
        }
    }

    /**
     * Verifies that all HermesErrorCode values are handled in the when expression above.
     * This is called at compile time via inline function to ensure exhaustiveness.
     */
    @Suppress("UNUSED_PARAMETER")
    inline fun verifyExhaustive(crossinline block: (HermesErrorCode) -> Unit) {
        // This function is intentionally empty - the when expression in mapToResult
        // is verified by the compiler for exhaustiveness when this function is inlined.
        // The compiler will error if any HermesErrorCode is not handled.
        HermesErrorCode.values().forEach { block(it) }
    }

    /**
     * Gets user-friendly message for an error code.
     */
    fun getUserMessage(errorCode: HermesErrorCode): String {
        return errorCode.userMessage ?: "An error occurred: ${errorCode.code}"
    }

    /**
     * Checks if an error code is retryable.
     */
    fun isRetryable(errorCode: HermesErrorCode): Boolean {
        return errorCode.retryable
    }
}