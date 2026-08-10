"""Central database primitives for TraderBot storage isolation."""

from .chroma_store import (
    ChromaOwnershipError,
    ChromaOwnershipLock,
    ChromaStore,
)
from .models import (
    ChromaCategoryError,
    ChromaDeleteRequest,
    ChromaGetRequest,
    ChromaQueryRequest,
    ChromaRecord,
)
from .pool import (
    ConnectionPoolClosedError,
    ConnectionPoolTimeoutError,
    CrossThreadAccessError,
    InvalidPoolConfigurationError,
    SQLiteConnectionPool,
)
from .security import (
    ChromaBackendError,
    InvalidChromaRootError,
    assert_embedded_backend,
    create_chroma_root,
    validate_chroma_root,
)

__all__ = [
    "ChromaBackendError",
    "ChromaCategoryError",
    "ChromaDeleteRequest",
    "ChromaGetRequest",
    "ChromaOwnershipError",
    "ChromaOwnershipLock",
    "ChromaQueryRequest",
    "ChromaRecord",
    "ChromaStore",
    "ConnectionPoolClosedError",
    "ConnectionPoolTimeoutError",
    "CrossThreadAccessError",
    "InvalidChromaRootError",
    "InvalidPoolConfigurationError",
    "SQLiteConnectionPool",
    "assert_embedded_backend",
    "create_chroma_root",
    "validate_chroma_root",
]
