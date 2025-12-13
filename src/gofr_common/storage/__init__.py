"""Storage module for GOFR services

Provides generic blob storage with metadata and group-based access control.
"""

from .base import StorageBase
from .file_storage import FileStorage
from .exceptions import (
    StorageError,
    PermissionDeniedError,
    ResourceNotFoundError,
    InvalidFormatError,
)
from .metadata import BlobMetadata

__all__ = [
    "StorageBase",
    "FileStorage",
    "StorageError",
    "PermissionDeniedError",
    "ResourceNotFoundError",
    "InvalidFormatError",
    "BlobMetadata",
]
