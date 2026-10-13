from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerState


def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=1.0, cooldown_seconds=0.1)

    for _ in range(2):
        try:
            raise RuntimeError("transient issue")
        except RuntimeError as exc:
            breaker.record_failure(exc)

    assert breaker.state == CircuitBreakerState.OPEN


def test_circuit_breaker_falls_back_to_fallback_after_open():
    breaker = CircuitBreaker(failure_threshold=1, timeout_seconds=0.5, cooldown_seconds=0.1)

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        breaker.record_failure(exc)

    assert breaker.state == CircuitBreakerState.OPEN

    fallback = lambda: {"status": "fallback"}
    result = breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("still down")), fallback=fallback)
    assert result == {"status": "fallback"}
