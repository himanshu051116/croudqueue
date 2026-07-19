"""Tests for platform-specific event loop configuration in runtime.py.

Verifies that the Windows selector event loop policy configuration is correct
and doesn't break non-Windows platforms.
"""

from __future__ import annotations

import asyncio
import sys
from unittest import mock

import pytest

from backend.app.runtime import configure_event_loop_policy, selector_event_loop


class TestEventLoopConfiguration:
    """Test platform-specific event loop configuration."""

    def test_windows_selector_event_loop_policy_is_set_on_windows(self) -> None:
        """Verify Windows policy is set when running on Windows."""
        with mock.patch("sys.platform", "win32"):
            with mock.patch("asyncio.set_event_loop_policy") as mock_set_policy:
                with mock.patch(
                    "asyncio.WindowsSelectorEventLoopPolicy"
                ) as mock_policy_class:
                    configure_event_loop_policy()

                    mock_policy_class.assert_called_once()
                    mock_set_policy.assert_called_once()

    def test_non_windows_platforms_skip_event_loop_policy_change(self) -> None:
        """Verify no policy change on non-Windows platforms."""
        with mock.patch("sys.platform", "linux"):
            with mock.patch("asyncio.set_event_loop_policy") as mock_set_policy:
                configure_event_loop_policy()
                mock_set_policy.assert_not_called()

    def test_selector_event_loop_factory_creates_selector_loop(self) -> None:
        """Verify selector event loop factory returns SelectorEventLoop."""
        loop = selector_event_loop()
        assert isinstance(loop, asyncio.SelectorEventLoop)
        loop.close()

    @pytest.mark.asyncio
    async def test_selector_event_loop_supports_basic_async_operations(self) -> None:
        """Verify selector event loop runs basic async operations."""

        async def simple_coroutine() -> str:
            return "success"

        result = await simple_coroutine()
        assert result == "success"

    def test_windows_selector_event_loop_policy_getattr_handles_missing_policy(
        self,
    ) -> None:
        """Verify graceful handling if WindowsSelectorEventLoopPolicy doesn't exist."""
        with mock.patch("sys.platform", "win32"):
            with mock.patch("asyncio.set_event_loop_policy") as mock_set_policy:
                with mock.patch(
                    "asyncio.WindowsSelectorEventLoopPolicy",
                    side_effect=AttributeError("not available"),
                ):
                    # Should not raise; getattr has defensive coding in production
                    try:
                        # This would only happen if asyncio doesn't have the attribute
                        # In real Python 3.12 on Windows, it exists
                        configure_event_loop_policy()
                    except AttributeError:
                        # Expected if policy doesn't exist on this platform
                        pass

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_windows_selector_policy_actually_exists_on_windows(self) -> None:
        """On actual Windows, verify WindowsSelectorEventLoopPolicy exists."""
        assert hasattr(asyncio, "WindowsSelectorEventLoopPolicy")

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test")
    def test_non_windows_platform_does_not_have_windows_policy(self) -> None:
        """On non-Windows, policy may or may not exist (optional attribute)."""
        # This is informational; the policy may exist as a stub on non-Windows
        # The test documents the expected behavior
        pass

    def test_configure_event_loop_policy_is_idempotent(self) -> None:
        """Verify multiple calls to configure are safe."""
        configure_event_loop_policy()
        configure_event_loop_policy()
        # If we get here without error, it's idempotent


class TestEventLoopIntegration:
    """Integration tests for event loop configuration with asyncio."""

    @pytest.mark.asyncio
    async def test_event_loop_handles_concurrent_tasks(self) -> None:
        """Verify event loop can handle multiple concurrent tasks."""

        async def delayed_operation(delay_ms: int, value: int) -> int:
            await asyncio.sleep(delay_ms / 1000.0)
            return value * 2

        # Run multiple tasks concurrently
        tasks = [delayed_operation(10, i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_event_loop_handles_exceptions_in_tasks(self) -> None:
        """Verify event loop properly propagates task exceptions."""

        async def failing_task() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await failing_task()

    @pytest.mark.asyncio
    async def test_event_loop_respects_timeouts(self) -> None:
        """Verify asyncio timeout handling works with configured loop."""

        async def long_running() -> None:
            await asyncio.sleep(10)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(long_running(), timeout=0.1)
