"""Error classification system for Sindri.

Provides a foundation for consistent error handling across the application.
Classifies errors into categories and provides actionable suggestions.
"""

import errno
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import structlog

log = structlog.get_logger()


class ErrorCategory(Enum):
    """Categories of errors for handling decisions."""

    TRANSIENT = "transient"   # Network, timeout, file lock - retry
    RESOURCE = "resource"     # VRAM, disk space - may recover with eviction
    FATAL = "fatal"           # Permissions, missing files - no retry
    AGENT = "agent"           # Stuck, max iterations - agent behavior issue


@dataclass
class ClassifiedError:
    """A classified error with handling metadata."""

    category: ErrorCategory
    message: str
    retryable: bool
    suggestion: Optional[str] = None
    original_exception: Optional[Exception] = None

    def __str__(self) -> str:
        """Human-readable error representation."""
        parts = [self.message]
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " | ".join(parts)


# OSError errno values that indicate transient failures
TRANSIENT_ERRNO = {
    errno.EAGAIN,      # Resource temporarily unavailable
    errno.EWOULDBLOCK, # Operation would block
    errno.EINTR,       # Interrupted system call
    errno.EBUSY,       # Device or resource busy
    errno.ENOBUFS,     # No buffer space available
    errno.ENOMEM,      # Out of memory (sometimes transient)
    errno.ETIMEDOUT,   # Connection timed out
    errno.ECONNRESET,  # Connection reset by peer
    errno.ECONNREFUSED,# Connection refused (service may restart)
    errno.EPIPE,       # Broken pipe
    errno.ENETUNREACH, # Network unreachable
    errno.EHOSTUNREACH,# Host unreachable
}

# Keywords that indicate VRAM/resource issues in error messages
VRAM_KEYWORDS = [
    "vram", "gpu memory", "cuda out of memory", "out of memory",
    "insufficient memory", "memory allocation", "rocm", "hip error"
]

# Suggestions for common error patterns
ERROR_SUGGESTIONS = {
    "file not found": "Try using list_directory to find the correct path",
    "no such file": "Try using list_directory to find the correct path",
    "permission denied": "Check file permissions or try a different location",
    "is a directory": "Expected a file path, not a directory",
    "not a directory": "Expected a directory path, not a file",
    "disk quota": "Free up disk space or use a different location",
    "no space left": "Free up disk space on the device",
    "connection refused": "Check if Ollama is running (sindri doctor)",
    "connection reset": "Network issue - will retry automatically",
    "timeout": "Operation timed out - will retry automatically",
    "vram": "Waiting for model eviction or try a smaller model",
    "out of memory": "Reduce memory usage or wait for resources",
    "model not found": "Check model name or pull with: ollama pull <model>",
    "invalid json": "Response format error - will retry",
    "rate limit": "API rate limited - will retry with backoff",
}


def classify_error(
    error: Exception,
    context: str = ""
) -> ClassifiedError:
    """Classify an exception for appropriate handling.

    Args:
        error: The exception to classify
        context: Optional context about where the error occurred

    Returns:
        ClassifiedError with category, retryability, and suggestions
    """
    error_msg = str(error).lower()
    error_type = type(error).__name__

    # Check for specific exception types first
    if isinstance(error, (ConnectionError, ConnectionRefusedError, ConnectionResetError)):
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            message=str(error),
            retryable=True,
            suggestion=_get_suggestion(error_msg),
            original_exception=error
        )

    if isinstance(error, TimeoutError):
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            message=str(error),
            retryable=True,
            suggestion="Operation timed out - will retry automatically",
            original_exception=error
        )

    if isinstance(error, PermissionError):
        return ClassifiedError(
            category=ErrorCategory.FATAL,
            message=str(error),
            retryable=False,
            suggestion="Check file permissions or try a different location",
            original_exception=error
        )

    if isinstance(error, FileNotFoundError):
        return ClassifiedError(
            category=ErrorCategory.FATAL,
            message=str(error),
            retryable=False,
            suggestion="Try using list_directory to find the correct path",
            original_exception=error
        )

    if isinstance(error, IsADirectoryError):
        return ClassifiedError(
            category=ErrorCategory.FATAL,
            message=str(error),
            retryable=False,
            suggestion="Expected a file path, not a directory",
            original_exception=error
        )

    if isinstance(error, NotADirectoryError):
        return ClassifiedError(
            category=ErrorCategory.FATAL,
            message=str(error),
            retryable=False,
            suggestion="Expected a directory path, not a file",
            original_exception=error
        )

    # Check for OSError with specific errno
    if isinstance(error, OSError) and hasattr(error, 'errno'):
        if error.errno in TRANSIENT_ERRNO:
            return ClassifiedError(
                category=ErrorCategory.TRANSIENT,
                message=str(error),
                retryable=True,
                suggestion=_get_suggestion(error_msg),
                original_exception=error
            )

    # Check for VRAM/memory issues in message
    if any(kw in error_msg for kw in VRAM_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.RESOURCE,
            message=str(error),
            retryable=True,  # May succeed after eviction
            suggestion="Waiting for model eviction or try a smaller model",
            original_exception=error
        )

    # Check for disk space issues
    if "no space left" in error_msg or "disk quota" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.RESOURCE,
            message=str(error),
            retryable=False,
            suggestion="Free up disk space on the device",
            original_exception=error
        )

    # Default: treat as fatal (don't retry unknown errors)
    return ClassifiedError(
        category=ErrorCategory.FATAL,
        message=str(error),
        retryable=False,
        suggestion=_get_suggestion(error_msg),
        original_exception=error
    )


def classify_error_message(
    error_msg: str,
    context: str = ""
) -> ClassifiedError:
    """Classify an error from its message string.

    Use this when you only have an error message, not an exception.

    Args:
        error_msg: The error message to classify
        context: Optional context about where the error occurred

    Returns:
        ClassifiedError with category, retryability, and suggestions
    """
    msg_lower = error_msg.lower()

    # Check for transient patterns
    transient_patterns = [
        "connection refused", "connection reset", "timeout",
        "temporarily unavailable", "try again", "busy",
        "rate limit", "too many requests"
    ]
    if any(p in msg_lower for p in transient_patterns):
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            message=error_msg,
            retryable=True,
            suggestion=_get_suggestion(msg_lower)
        )

    # Check for resource patterns
    if any(kw in msg_lower for kw in VRAM_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.RESOURCE,
            message=error_msg,
            retryable=True,
            suggestion="Waiting for model eviction or try a smaller model"
        )

    # Check for fatal patterns
    fatal_patterns = [
        "permission denied", "access denied", "not found",
        "no such file", "is a directory", "not a directory",
        "invalid", "malformed"
    ]
    if any(p in msg_lower for p in fatal_patterns):
        return ClassifiedError(
            category=ErrorCategory.FATAL,
            message=error_msg,
            retryable=False,
            suggestion=_get_suggestion(msg_lower)
        )

    # Default: assume fatal (safer to not retry unknowns)
    return ClassifiedError(
        category=ErrorCategory.FATAL,
        message=error_msg,
        retryable=False,
        suggestion=_get_suggestion(msg_lower)
    )


def _get_suggestion(error_msg: str) -> Optional[str]:
    """Get a suggestion for an error message.

    Args:
        error_msg: Lowercase error message

    Returns:
        Suggestion string or None
    """
    for pattern, suggestion in ERROR_SUGGESTIONS.items():
        if pattern in error_msg:
            return suggestion
    return None


def is_retryable(error: Exception) -> bool:
    """Quick check if an error should be retried.

    Args:
        error: The exception to check

    Returns:
        True if the error is likely transient and worth retrying
    """
    return classify_error(error).retryable


def get_error_suggestion(error: Exception) -> Optional[str]:
    """Get a suggestion for handling an error.

    Args:
        error: The exception to get suggestion for

    Returns:
        Suggestion string or None
    """
    return classify_error(error).suggestion
