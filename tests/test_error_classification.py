"""Tests for error classification system."""

import errno

from sindri.core.errors import (
    ErrorCategory,
    ClassifiedError,
    classify_error,
    classify_error_message,
    is_retryable,
    get_error_suggestion,
)


class TestErrorCategory:
    """Test ErrorCategory enum."""

    def test_categories_exist(self):
        """All expected categories should exist."""
        assert ErrorCategory.TRANSIENT.value == "transient"
        assert ErrorCategory.RESOURCE.value == "resource"
        assert ErrorCategory.FATAL.value == "fatal"
        assert ErrorCategory.AGENT.value == "agent"


class TestClassifiedError:
    """Test ClassifiedError dataclass."""

    def test_basic_creation(self):
        """Should create a classified error."""
        err = ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            message="Connection refused",
            retryable=True,
            suggestion="Check if Ollama is running",
        )
        assert err.category == ErrorCategory.TRANSIENT
        assert err.message == "Connection refused"
        assert err.retryable is True
        assert err.suggestion == "Check if Ollama is running"

    def test_str_representation(self):
        """Should format error as string."""
        err = ClassifiedError(
            category=ErrorCategory.FATAL,
            message="File not found",
            retryable=False,
            suggestion="Try list_directory",
        )
        result = str(err)
        assert "File not found" in result
        assert "Try list_directory" in result

    def test_str_without_suggestion(self):
        """Should format error without suggestion."""
        err = ClassifiedError(
            category=ErrorCategory.FATAL, message="Unknown error", retryable=False
        )
        assert str(err) == "Unknown error"


class TestClassifyError:
    """Test classify_error function with real exceptions."""

    def test_connection_error(self):
        """ConnectionError should be classified as transient."""
        error = ConnectionError("Connection refused")
        result = classify_error(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True
        assert result.original_exception is error

    def test_connection_refused_error(self):
        """ConnectionRefusedError should be transient."""
        error = ConnectionRefusedError("Connection refused")
        result = classify_error(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True

    def test_timeout_error(self):
        """TimeoutError should be transient."""
        error = TimeoutError("Operation timed out")
        result = classify_error(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True
        assert "timed out" in result.suggestion.lower()

    def test_permission_error(self):
        """PermissionError should be fatal."""
        error = PermissionError("Permission denied: /etc/passwd")
        result = classify_error(error)

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False
        assert "permission" in result.suggestion.lower()

    def test_file_not_found_error(self):
        """FileNotFoundError should be fatal with suggestion."""
        error = FileNotFoundError("No such file: /foo/bar.txt")
        result = classify_error(error)

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False
        assert "list_directory" in result.suggestion

    def test_is_directory_error(self):
        """IsADirectoryError should be fatal."""
        error = IsADirectoryError("Is a directory: /tmp")
        result = classify_error(error)

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False
        assert "directory" in result.suggestion.lower()

    def test_not_a_directory_error(self):
        """NotADirectoryError should be fatal."""
        error = NotADirectoryError("Not a directory: /tmp/file.txt")
        result = classify_error(error)

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False

    def test_oserror_transient_errno(self):
        """OSError with transient errno should be retryable."""
        error = OSError(errno.EAGAIN, "Resource temporarily unavailable")
        result = classify_error(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True

    def test_oserror_connection_reset(self):
        """OSError with ECONNRESET should be transient."""
        error = OSError(errno.ECONNRESET, "Connection reset by peer")
        result = classify_error(error)

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True

    def test_vram_error_from_message(self):
        """VRAM errors should be classified as resource."""
        error = RuntimeError("CUDA out of memory. Tried to allocate 2GB")
        result = classify_error(error)

        assert result.category == ErrorCategory.RESOURCE
        assert result.retryable is True
        assert "model" in result.suggestion.lower()

    def test_gpu_memory_error(self):
        """GPU memory errors should be resource category."""
        error = RuntimeError("GPU memory allocation failed")
        result = classify_error(error)

        assert result.category == ErrorCategory.RESOURCE
        assert result.retryable is True

    def test_disk_space_error(self):
        """Disk space errors should be resource but not retryable."""
        error = OSError("No space left on device")
        result = classify_error(error)

        assert result.category == ErrorCategory.RESOURCE
        assert result.retryable is False
        assert "disk space" in result.suggestion.lower()

    def test_unknown_error_is_fatal(self):
        """Unknown errors should default to fatal."""
        error = ValueError("Some unknown error")
        result = classify_error(error)

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False


class TestClassifyErrorMessage:
    """Test classify_error_message function."""

    def test_connection_refused_message(self):
        """Connection refused in message should be transient."""
        result = classify_error_message("Error: connection refused")

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True

    def test_timeout_message(self):
        """Timeout in message should be transient."""
        result = classify_error_message("Request timeout after 30s")

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True

    def test_rate_limit_message(self):
        """Rate limit in message should be transient."""
        result = classify_error_message("Rate limit exceeded, try again later")

        assert result.category == ErrorCategory.TRANSIENT
        assert result.retryable is True

    def test_permission_denied_message(self):
        """Permission denied in message should be fatal."""
        result = classify_error_message("Permission denied: /etc/shadow")

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False

    def test_not_found_message(self):
        """Not found in message should be fatal."""
        result = classify_error_message("File not found: config.yaml")

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False
        assert "list_directory" in result.suggestion

    def test_vram_message(self):
        """VRAM in message should be resource."""
        result = classify_error_message("Insufficient VRAM for model")

        assert result.category == ErrorCategory.RESOURCE
        assert result.retryable is True

    def test_unknown_message_is_fatal(self):
        """Unknown messages should default to fatal."""
        result = classify_error_message("Something weird happened")

        assert result.category == ErrorCategory.FATAL
        assert result.retryable is False


class TestHelperFunctions:
    """Test helper functions."""

    def test_is_retryable_true(self):
        """is_retryable should return True for transient errors."""
        error = ConnectionError("Connection refused")
        assert is_retryable(error) is True

    def test_is_retryable_false(self):
        """is_retryable should return False for fatal errors."""
        error = FileNotFoundError("No such file")
        assert is_retryable(error) is False

    def test_get_error_suggestion_exists(self):
        """get_error_suggestion should return suggestion when available."""
        error = FileNotFoundError("No such file")
        suggestion = get_error_suggestion(error)
        assert suggestion is not None
        assert "list_directory" in suggestion

    def test_get_error_suggestion_none(self):
        """get_error_suggestion may return None for unknown errors."""
        error = ValueError("Unknown error xyz123")
        suggestion = get_error_suggestion(error)
        # May or may not have suggestion depending on message
        assert suggestion is None or isinstance(suggestion, str)
