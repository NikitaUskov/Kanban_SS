"""In-process write serialization for SQLite mutations."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock


class WriteCoordinator:
    """Serialize all database writes in the single Uvicorn process."""

    def __init__(self) -> None:
        self._lock = RLock()

    @contextmanager
    def write(self) -> Iterator[None]:
        """Hold the shared re-entrant lock for one complete transaction."""

        with self._lock:
            yield


write_coordinator = WriteCoordinator()

