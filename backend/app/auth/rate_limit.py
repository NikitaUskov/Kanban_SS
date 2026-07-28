"""In-memory login throttling for the single backend process."""

from collections import defaultdict, deque
from threading import Lock

from app.config import get_settings
from app.timeutils import utcnow


class LoginAttemptLimiter:
    """Track failed attempts by normalized IP and username."""

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _trim(self, values: deque[float], now: float) -> None:
        window = get_settings().login_attempt_window_minutes * 60
        while values and values[0] <= now - window:
            values.popleft()

    def is_blocked(self, ip_address: str, username: str) -> tuple[bool, int]:
        key = (ip_address, username.lower())
        now = utcnow().timestamp()
        with self._lock:
            values = self._attempts[key]
            self._trim(values, now)
            if len(values) < get_settings().login_attempt_limit:
                return False, 0
            retry_after = max(
                1,
                int(values[0] + get_settings().login_attempt_window_minutes * 60 - now),
            )
            return True, retry_after

    def record_failure(self, ip_address: str, username: str) -> None:
        key = (ip_address, username.lower())
        now = utcnow().timestamp()
        with self._lock:
            values = self._attempts[key]
            self._trim(values, now)
            values.append(now)

    def clear(self, ip_address: str, username: str) -> None:
        with self._lock:
            self._attempts.pop((ip_address, username.lower()), None)


login_limiter = LoginAttemptLimiter()

