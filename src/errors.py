"""Shared exception types for file-level problems that must stop processing."""


class InputFileError(Exception):
    """Raised when an input file or its schema is unusable (stops the run)."""