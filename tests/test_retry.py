import asyncio
from typing import Any

import pytest

from tunarag import AdapterError, RetryPolicy


def test_retry_policy_bounds_attempts_backoff_and_timeouts() -> None:
    policy = RetryPolicy(
        max_retries=3,
        sample_timeout_seconds=2.0,
        trial_timeout_seconds=10.0,
        base_delay_seconds=0.5,
        max_delay_seconds=1.5,
    )

    assert policy.max_attempts == 4
    assert policy.lease_seconds == 70.0
    assert [policy.delay_before_retry(index) for index in range(4)] == [0.5, 1.0, 1.5, 1.5]


def test_retry_policy_classifies_only_explicit_transient_failures() -> None:
    policy = RetryPolicy()

    assert policy.is_retryable(ConnectionError())
    assert policy.is_retryable(TimeoutError())
    assert policy.is_retryable(asyncio.TimeoutError())
    assert policy.is_retryable(AdapterError("transient", retryable=True))
    assert not policy.is_retryable(AdapterError("permanent"))
    assert not policy.is_retryable(ValueError())


@pytest.mark.parametrize(
    "arguments",
    [
        {"max_retries": -1},
        {"max_retries": 1.5},
        {"sample_timeout_seconds": 0},
        {"trial_timeout_seconds": float("inf")},
        {"base_delay_seconds": -1},
        {"base_delay_seconds": 2, "max_delay_seconds": 1},
    ],
)
def test_retry_policy_rejects_invalid_bounds(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**arguments)
