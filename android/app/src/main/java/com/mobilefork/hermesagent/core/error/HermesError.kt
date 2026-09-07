package com.mobilefork.hermesagent.core.error

data class HermesError(
    val code: String,
    override val message: String,
    val retryable: Boolean = false,
    val details: Map<String, Any> = emptyMap(),
    override val cause: Throwable? = null,
) : Throwable(message, cause) {

    companion object {
        /** Convenience factory: HermesError(HermesErrorCode.X, "msg"[, cause = e]) */
        operator fun invoke(
            code: HermesErrorCode,
            message: String? = null,
            details: Map<String, Any> = emptyMap(),
            cause: Throwable? = null,
        ): HermesError = fromCode(code, message, details, cause)

        fun fromCode(
            errorCode: HermesErrorCode,
            message: String? = null,
            details: Map<String, Any> = emptyMap(),
            cause: Throwable? = null,
        ): HermesError {
            return HermesError(
                code = errorCode.code,
                message = message ?: errorCode.userMessage ?: "Error",
                retryable = errorCode.retryable,
                details = details,
                cause = cause,
            )
        }

        fun fromException(e: Throwable): HermesError {
            return when (e) {
                is HermesError -> e
                else -> HermesError(
                    code = HermesErrorCode.INTERNAL_ERROR.code,
                    message = e.message ?: e.javaClass.simpleName,
                    retryable = true,
                    cause = e,
                )
            }
        }
    }

    fun isRetryable(): Boolean = retryable
}
