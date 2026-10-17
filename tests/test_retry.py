"""Tests for retry decorator with exponential backoff."""

from unittest.mock import MagicMock
import pytest

from src.kites_automate.utils.retry import retry_with_backoff


def test_retry_success_on_first_try():
    mock_fn = MagicMock(return_value="success")
    decorated = retry_with_backoff(retries=3, initial_delay=0.01)(mock_fn)

    res = decorated()
    assert res == "success"
    assert mock_fn.call_count == 1


def test_retry_eventual_success():
    mock_fn = MagicMock(side_effect=[ValueError("Temporary 1"), ValueError("Temporary 2"), "recovered"])
    decorated = retry_with_backoff(retries=4, initial_delay=0.01, exceptions=(ValueError,))(mock_fn)

    res = decorated()
    assert res == "recovered"
    assert mock_fn.call_count == 3


def test_retry_exhausted_raises():
    mock_fn = MagicMock(side_effect=RuntimeError("Persistent error"))
    decorated = retry_with_backoff(retries=2, initial_delay=0.01, exceptions=(RuntimeError,))(mock_fn)

    with pytest.raises(RuntimeError, match="Persistent error"):
        decorated()
    assert mock_fn.call_count == 2
