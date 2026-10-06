"""Shared exception types for VritraAI assistant core."""

class VritraAIError(Exception):
    """Base exception for VritraAI."""
    pass

class NetworkError(VritraAIError):
    """Raised when network operations fail."""
    pass

class APIError(VritraAIError):
    """Raised when AI API operations fail."""
    pass

class FileOperationError(VritraAIError):
    """Raised when file operations fail."""
    pass

