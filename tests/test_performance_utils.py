"""
Tests for performance_utils.py module.

This module contains comprehensive tests for the performance monitoring,
resource optimization, and parallel execution utilities.
"""

import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from run_bitcoin_tests.performance_utils import (
    ParallelExecutor,
    PerformanceMonitor,
    ResourceOptimizer,
    get_performance_monitor,
    optimize_system_resources,
    with_performance_monitoring,
)


class TestPerformanceMonitor:
    """Test cases for PerformanceMonitor class."""

    def test_initialization(self) -> None:
        """Test PerformanceMonitor initialization."""
        monitor = PerformanceMonitor(interval=0.1)
        assert monitor.interval == 0.1
        assert not monitor._monitoring
        assert monitor._thread is None
        assert monitor._metrics == []

    def test_start_stop_monitoring(self) -> None:
        """Test starting and stopping performance monitoring."""
        monitor = PerformanceMonitor(interval=0.01)

        # Start monitoring
        monitor.start_monitoring()
        assert monitor._monitoring
        assert monitor._thread is not None
        assert monitor._thread.is_alive()

        # Wait a bit for some metrics to be collected
        time.sleep(0.05)

        # Stop monitoring
        metrics = monitor.stop_monitoring()
        assert not monitor._monitoring
        assert len(metrics) > 0

    def test_start_monitoring_already_started(self) -> None:
        """Test starting monitoring when already started."""
        monitor = PerformanceMonitor(interval=0.01)

        # Start monitoring
        monitor.start_monitoring()
        assert monitor._monitoring

        # Try to start again (should be ignored)
        monitor.start_monitoring()
        assert monitor._monitoring

        # Stop monitoring
        monitor.stop_monitoring()

    @patch(
        "run_bitcoin_tests.performance_utils.PerformanceMonitor._collect_metrics",
        side_effect=Exception("Collection error"),
    )
    @patch("run_bitcoin_tests.performance_utils.logger")
    def test_monitoring_collect_metrics_exception(self, mock_logger, mock_collect) -> None:
        """Test that monitoring loop handles _collect_metrics exceptions."""
        monitor = PerformanceMonitor(interval=0.01)

        # Start monitoring
        monitor.start_monitoring()

        # Wait a bit for the monitoring loop to run
        time.sleep(0.05)

        # Stop monitoring
        monitor.stop_monitoring()

        # Should have logged the warning
        mock_logger.warning.assert_called()

    def test_stop_monitoring_not_started(self) -> None:
        """Test stopping monitoring when not started."""
        monitor = PerformanceMonitor()

        # Stop monitoring when not started (should return empty metrics)
        metrics = monitor.stop_monitoring()
        assert metrics == []
        assert not monitor._monitoring

        # Verify metrics structure
        for metric in metrics:
            assert "timestamp" in metric
            assert "cpu_percent" in metric
            assert "memory_percent" in metric
            assert isinstance(metric["timestamp"], float)
            assert isinstance(metric["cpu_percent"], (int, float))

    def test_monitoring_context(self) -> None:
        """Test that monitoring stops when interrupted."""
        monitor = PerformanceMonitor(interval=0.01)
        monitor.start_monitoring()

        # Simulate some monitoring time
        time.sleep(0.03)

        # Stop and get metrics
        metrics = monitor.stop_monitoring()
        assert len(metrics) > 0

    @patch("run_bitcoin_tests.performance_utils.psutil.cpu_percent")
    @patch("run_bitcoin_tests.performance_utils.psutil.virtual_memory")
    @patch("run_bitcoin_tests.performance_utils.psutil.disk_usage")
    @patch("run_bitcoin_tests.performance_utils.psutil.net_io_counters")
    def test_collect_metrics(self, mock_net, mock_disk, mock_memory, mock_cpu) -> None:
        """Test metrics collection with mocked system calls."""
        # Setup mocks
        mock_cpu.return_value = 45.5
        mock_memory.return_value = Mock(percent=60.2, used=4.2 * 1024**3, available=2.8 * 1024**3)
        mock_disk.return_value = Mock(percent=75.1, used=150 * 1024**3, free=50 * 1024**3)
        mock_net.return_value = Mock(bytes_sent=1024 * 1024, bytes_recv=2 * 1024 * 1024)

        monitor = PerformanceMonitor()
        metrics = monitor._collect_metrics()

        assert metrics["cpu_percent"] == 45.5
        assert metrics["memory_percent"] == 60.2
        assert abs(metrics["memory_used_gb"] - 4.2) < 0.1
        assert abs(metrics["memory_available_gb"] - 2.8) < 0.1
        assert metrics["disk_percent"] == 75.1
        assert abs(metrics["disk_used_gb"] - 150) < 0.1
        assert abs(metrics["disk_free_gb"] - 50) < 0.1
        assert metrics["network_bytes_sent"] == 1024 * 1024
        assert metrics["network_bytes_recv"] == 2 * 1024 * 1024

    def test_error_handling_in_metrics_collection(self) -> None:
        """Test that metrics collection handles errors gracefully."""
        monitor = PerformanceMonitor()

        # Mock psutil to raise exception
        with patch(
            "run_bitcoin_tests.performance_utils.psutil.cpu_percent",
            side_effect=Exception("Test error"),
        ):
            metrics = monitor._collect_metrics()
            assert "error" in metrics
            assert "Test error" in metrics["error"]


class TestResourceOptimizer:
    """Test cases for ResourceOptimizer class."""

    @patch("run_bitcoin_tests.performance_utils.multiprocessing.cpu_count", return_value=8)
    @patch("run_bitcoin_tests.performance_utils.psutil.virtual_memory")
    def test_get_optimal_parallel_jobs(self, mock_memory, mock_cpu_count) -> None:
        """Test optimal parallel job calculation."""
        mock_memory.return_value.total = 16 * 1024**3  # 16GB

        optimal = ResourceOptimizer.get_optimal_parallel_jobs()
        # Should be min(8, 16/2) = min(8, 8) = 8
        assert optimal == 8

        # Test with memory limit
        mock_memory.return_value.total = 4 * 1024**3  # 4GB
        optimal = ResourceOptimizer.get_optimal_parallel_jobs()
        # Should be min(8, 4/2) = min(8, 2) = 2
        assert optimal == 2

        # Test with explicit limit (reset memory to high value)
        mock_memory.return_value.total = 16 * 1024**3  # 16GB
        optimal = ResourceOptimizer.get_optimal_parallel_jobs(max_jobs=4)
        assert optimal == 4

    @patch("run_bitcoin_tests.performance_utils.multiprocessing.cpu_count", return_value=1)
    def test_minimum_jobs(self, mock_cpu_count) -> None:
        """Test that at least 1 job is always returned."""
        optimal = ResourceOptimizer.get_optimal_parallel_jobs()
        assert optimal >= 1

    @patch(
        "run_bitcoin_tests.performance_utils.psutil.virtual_memory",
        side_effect=Exception("Memory info error"),
    )
    @patch("run_bitcoin_tests.performance_utils.multiprocessing.cpu_count", return_value=4)
    def test_get_optimal_parallel_jobs_exception(self, mock_cpu_count, mock_memory) -> None:
        """Test get_optimal_parallel_jobs handles exceptions."""
        optimal = ResourceOptimizer.get_optimal_parallel_jobs()
        # Should fallback to conservative default: max(1, 4 // 2) = 2
        assert optimal == 2

    @patch("run_bitcoin_tests.performance_utils.platform.system", return_value="Linux")
    def test_optimize_process_priority_linux(self, mock_platform) -> None:
        """Test process priority optimization on Linux."""
        import sys

        if sys.platform == "win32":
            pytest.skip("os.nice not available on Windows")
        with patch("os.nice") as mock_nice:
            ResourceOptimizer.optimize_process_priority()
            mock_nice.assert_called_once_with(-5)

    @patch("run_bitcoin_tests.performance_utils.platform.system", return_value="Windows")
    def test_optimize_process_priority_windows(self, mock_platform) -> None:
        """Test process priority optimization on Windows (should do nothing)."""
        ResourceOptimizer.optimize_process_priority()
        # Should not attempt to change priority on Windows

    @patch("run_bitcoin_tests.performance_utils.platform.system", return_value="Linux")
    def test_optimize_process_priority_exception(self, mock_platform) -> None:
        """Test optimize_process_priority handles exceptions gracefully."""
        import sys

        if sys.platform == "win32":
            pytest.skip("os.nice not available on Windows")
        with patch("os.nice", side_effect=OSError("Permission denied")):
            # Should not raise exception
            ResourceOptimizer.optimize_process_priority()

    @patch("run_bitcoin_tests.performance_utils.gc.collect")
    def test_cleanup_memory(self, mock_gc) -> None:
        """Test memory cleanup."""
        ResourceOptimizer.cleanup_memory()
        mock_gc.assert_called_once()

    @patch(
        "run_bitcoin_tests.performance_utils.ResourceOptimizer.get_optimal_parallel_jobs",
        return_value=4,
    )
    @patch("run_bitcoin_tests.performance_utils.psutil.disk_usage")
    @patch("run_bitcoin_tests.performance_utils.psutil.virtual_memory")
    @patch("run_bitcoin_tests.performance_utils.psutil.cpu_freq")
    @patch("run_bitcoin_tests.performance_utils.multiprocessing.cpu_count", return_value=4)
    @patch("run_bitcoin_tests.performance_utils.platform.platform", return_value="Linux-5.4.0")
    @patch("run_bitcoin_tests.performance_utils.platform.python_version", return_value="3.9.0")
    def test_get_system_info(
        self,
        mock_py_version,
        mock_platform,
        mock_cpu_count,
        mock_cpu_freq,
        mock_memory,
        mock_disk,
        mock_get_jobs,
    ):
        """Test system information collection."""
        mock_memory.return_value.total = 8 * 1024**3
        mock_memory.return_value.available = 6 * 1024**3
        mock_cpu_freq.return_value.current = 2500.0
        mock_disk.return_value.total = 100 * 1024**3
        mock_disk.return_value.free = 50 * 1024**3

        info = ResourceOptimizer.get_system_info()

        assert info["cpu_count"] == 4
        assert info["cpu_freq"] == 2500.0
        assert abs(info["memory_total_gb"] - 8.0) < 0.1
        assert abs(info["memory_available_gb"] - 6.0) < 0.1
        assert info["platform"] == "Linux-5.4.0"
        assert info["python_version"] == "3.9.0"

    def test_get_system_info_error_handling(self) -> None:
        """Test system info collection handles errors."""
        with patch(
            "run_bitcoin_tests.performance_utils.psutil.virtual_memory",
            side_effect=Exception("Test error"),
        ):
            info = ResourceOptimizer.get_system_info()
            assert isinstance(info, dict)
            # Should return empty dict or handle gracefully
            assert "error" not in info or isinstance(info.get("error"), str)


class TestParallelExecutor:
    """Test cases for ParallelExecutor class."""

    def test_initialization(self) -> None:
        """Test ParallelExecutor initialization."""
        executor = ParallelExecutor(max_workers=4)
        assert executor.max_workers == 4
        assert executor._executor is None

    def test_context_manager(self) -> None:
        """Test ParallelExecutor as context manager."""
        executor = ParallelExecutor(max_workers=2)
        with executor:
            assert executor._executor is not None
            assert executor._executor._max_workers == 2

        # Should be cleaned up after context
        assert executor._executor is None

    def test_execute_parallel(self) -> None:
        """Test parallel execution of tasks."""

        def add_numbers(x, y):
            time.sleep(0.01)  # Simulate work
            return x + y

        tasks = [(add_numbers, (1, 2), {}), (add_numbers, (3, 4), {}), (add_numbers, (5, 6), {})]

        with ParallelExecutor(max_workers=2) as executor:
            results = executor.execute_parallel(tasks)

        assert results == [3, 7, 11]

    def test_execute_parallel_with_errors(self) -> None:
        """Test parallel execution handles errors gracefully."""

        def success_task():
            return "success"

        def error_task():
            raise ValueError("Test error")

        tasks = [(success_task, (), {}), (error_task, (), {}), (success_task, (), {})]

        with ParallelExecutor(max_workers=2) as executor:
            results = executor.execute_parallel(tasks)

        assert results[0] == "success"
        assert results[1] is None  # Error case
        assert results[2] == "success"

    def test_map_parallel(self) -> None:
        """Test parallel map functionality."""

        def square(x):
            time.sleep(0.01)
            return x * x

        items = [1, 2, 3, 4, 5]

        with ParallelExecutor(max_workers=2) as executor:
            results = executor.map_parallel(square, items)

        assert len(results) == 5
        assert 1 in results
        assert 4 in results
        assert 9 in results
        assert 16 in results
        assert 25 in results

    def test_error_when_not_in_context(self) -> None:
        """Test that operations fail when not in context manager."""
        executor = ParallelExecutor()

        with pytest.raises(RuntimeError, match="ParallelExecutor must be used as context manager"):
            executor.execute_parallel([])

        with pytest.raises(RuntimeError, match="ParallelExecutor must be used as context manager"):
            executor.map_parallel(lambda x: x, [])


class TestGlobalFunctions:
    """Test global functions in performance_utils."""

    def test_get_performance_monitor_singleton(self) -> None:
        """Test that get_performance_monitor returns singleton instances."""
        # Reset the singleton for this test
        import run_bitcoin_tests.performance_utils as pu

        pu._performance_monitor = None

        monitor1 = get_performance_monitor(interval=0.1)
        monitor2 = get_performance_monitor(interval=0.2)

        # Should return the same instance
        assert monitor1 is monitor2
        assert monitor1.interval == 0.1  # First call sets the interval

    @patch("run_bitcoin_tests.performance_utils.ResourceOptimizer.optimize_process_priority")
    @patch("run_bitcoin_tests.performance_utils.ResourceOptimizer.cleanup_memory")
    @patch("run_bitcoin_tests.performance_utils.ResourceOptimizer.get_system_info")
    def test_optimize_system_resources(self, mock_get_info, mock_cleanup, mock_optimize) -> None:
        """Test system resource optimization."""
        mock_get_info.return_value = {"cpu_count": 4, "memory_total_gb": 8.0}

        optimize_system_resources()

        mock_optimize.assert_called_once()
        mock_cleanup.assert_called_once()
        mock_get_info.assert_called_once()

    @patch(
        "run_bitcoin_tests.performance_utils.ResourceOptimizer.optimize_process_priority",
        side_effect=Exception("Priority error"),
    )
    @patch("run_bitcoin_tests.performance_utils.ResourceOptimizer.cleanup_memory")
    @patch("run_bitcoin_tests.performance_utils.ResourceOptimizer.get_system_info")
    @patch("run_bitcoin_tests.performance_utils.logger")
    def test_optimize_system_resources_exception(
        self, mock_logger, mock_get_info, mock_cleanup, mock_optimize
    ):
        """Test optimize_system_resources handles exceptions gracefully."""
        mock_get_info.return_value = {"cpu_count": 4, "memory_total_gb": 8.0}

        # Should not raise exception
        optimize_system_resources()

        # Should log the warning
        mock_logger.warning.assert_called_once()

    def test_with_performance_monitoring_decorator(self) -> None:
        """Test the performance monitoring decorator."""

        @with_performance_monitoring
        def test_function():
            time.sleep(0.02)  # Simulate work
            return "result"

        result = test_function()

        assert result == "result"

        # Note: In a real scenario, this would log performance metrics
        # but we can't easily test the logging output here


class TestIntegration:
    """Integration tests for performance utilities."""

    def test_full_performance_workflow(self) -> None:
        """Test a complete performance monitoring workflow."""
        # Start monitoring
        monitor = get_performance_monitor(interval=0.01)
        monitor.start_monitoring()

        # Simulate some work
        time.sleep(0.05)

        # Get metrics
        metrics = monitor.stop_monitoring()

        assert len(metrics) > 0
        assert all("cpu_percent" in m for m in metrics)
        assert all("memory_percent" in m for m in metrics)

    def test_resource_optimization_workflow(self) -> None:
        """Test resource optimization workflow."""
        # This is mainly a smoke test since we can't easily test
        # actual system resource changes
        optimize_system_resources()

        # Should not raise any exceptions
        assert True

    @patch(
        "run_bitcoin_tests.performance_utils.ResourceOptimizer.get_optimal_parallel_jobs",
        return_value=2,
    )
    def test_parallel_processing_workflow(self, mock_optimal) -> None:
        """Test parallel processing workflow."""

        def process_item(item):
            time.sleep(0.01)
            return item * 2

        items = [1, 2, 3, 4]

        with ParallelExecutor() as executor:
            results = executor.map_parallel(process_item, items)

        assert sorted(results) == [2, 4, 6, 8]
