from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional


class AdmissionError(RuntimeError):
    """Raised when a request is rejected by the admission gate."""


@dataclass
class TokenBucket:
    capacity: int
    refill_rate: float
    tokens: float
    updated_at: float
    lock: threading.Lock

    def __init__(self, capacity: int, refill_rate: float, initial_tokens: Optional[float] = None):
        self.capacity = max(1, capacity)
        self.refill_rate = max(0.0, refill_rate)
        self.tokens = float(initial_tokens if initial_tokens is not None else capacity)
        self.updated_at = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = max(0.0, now - self.updated_at)
            self.updated_at = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False


class AdmissionController:
    """Simple rate limiter and concurrency gate for upstream inference requests."""

    def __init__(self, rate_limit_per_second: float = 10.0, bucket_capacity: int = 20, max_concurrency: int = 8):
        self.rate_limiter = TokenBucket(capacity=bucket_capacity, refill_rate=rate_limit_per_second, initial_tokens=bucket_capacity)
        self.max_concurrency = max(1, max_concurrency)
        self.active_requests = 0
        self.lock = threading.Lock()

    def allow(self, tokens: float = 1.0) -> bool:
        with self.lock:
            if self.active_requests >= self.max_concurrency:
                return False
            if not self.rate_limiter.consume(tokens):
                return False
            self.active_requests += 1
            return True

    def release(self) -> None:
        with self.lock:
            self.active_requests = max(0, self.active_requests - 1)

    def __enter__(self):
        if not self.allow():
            raise AdmissionError("Request rejected by admission gate; capacity exhausted.")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
