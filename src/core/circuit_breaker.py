from __future__ import annotations

import random
import threading
import time
from collections import deque
from enum import Enum
from typing import Any, Callable, Deque, Optional


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(RuntimeError):
    pass


class CircuitBreaker:
    """Deterministic state machine with exponential backoff and jitter."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 8.0,
        cooldown_seconds: float = 30.0,
        half_open_max_calls: int = 2,
        should_retry: Optional[Callable[[Exception], bool]] = None,
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls
        self.should_retry = should_retry or (lambda exc: True)
        self.state = CircuitBreakerState.CLOSED
        self.consecutive_failures = 0
        self.opened_at: Optional[float] = None
        self.last_failure_at: Optional[float] = None
        self._lock = threading.Lock()
        self._half_open_calls = 0
        self._history: Deque[bool] = deque(maxlen=10)

    def _now(self) -> float:
        return time.monotonic()

    def _can_attempt_reset(self) -> bool:
        return self.opened_at is not None and (self._now() - self.opened_at) >= self.cooldown_seconds

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._can_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                    self._half_open_calls = 0
                    return True
                return False
            if self.state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._history.append(True)
            self.consecutive_failures = 0
            self.state = CircuitBreakerState.CLOSED
            self.opened_at = None
            self.last_failure_at = None
            self._half_open_calls = 0

    def record_failure(self, exc: Exception) -> None:
        with self._lock:
            self._history.append(False)
            self.consecutive_failures += 1
            self.last_failure_at = self._now()
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.OPEN
                self.opened_at = self._now()
                return
            if self.consecutive_failures >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                self.opened_at = self._now()

    def call(self, operation: Callable[[], Any], fallback: Optional[Callable[[], Any]] = None, *, allowed_exceptions=(Exception,)):
        if not self.allow_request():
            if fallback is not None:
                return fallback()
            raise CircuitBreakerError("Circuit is open; upstream requests are being throttled.")

        try:
            result = operation()
            self.record_success()
            return result
        except allowed_exceptions as exc:
            self.record_failure(exc)
            if fallback is not None:
                return fallback()
            raise

    def backoff_seconds(self, attempt_number: int) -> float:
        base = min(self.cooldown_seconds, 2 ** max(0, attempt_number))
        return base * random.uniform(0.5, 1.5)
