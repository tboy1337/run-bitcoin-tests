"""
Performance optimization utilities for the Bitcoin Core tests runner.

This module provides utilities for optimizing various aspects of the
testing pipeline, including memory management, CPU optimization, and
resource monitoring.

Key Features:
- Memory usage monitoring and optimization
- CPU usage optimization
- Disk I/O optimization
- Parallel processing utilities
- Resource cleanup and optimization

Classes:
    PerformanceMonitor: Monitor system resources during operations
    ResourceOptimizer: Optimize resource usage for better performance
    ParallelExecutor: Execute operations in parallel where beneficial
"""

import logging
import multiprocessing
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple, TypeVar, Union

import psutil

T = TypeVar("T")

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Monitor system performance metrics during operations.

    Provides real-time monitoring of CPU, memory, disk, and network usage
    to help optimize performance and identify bottlenecks.
    """

    def __init__(self, interval: float = 1.0):
        """
        Initialize performance monitor.

        Args:
            interval: Monitoring interval in seconds
        """
        self.interval = interval
        self._monitoring = False
        self._thread: Optional[threading.Thread] = None
        self._metrics: List[Dict[str, Union[float, int, str, None, Tuple[float, float, float]]]] = (
            []
        )
        self._lock = threading.Lock()

    def start_monitoring(self) -> None:
        """Start performance monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.debug("Performance monitoring started")

    def stop_monitoring(
        self,
    ) -> List[Dict[str, Union[float, int, str, None, Tuple[float, float, float]]]]:
        """Stop monitoring and return collected metrics."""
        if not self._monitoring:
            return self._metrics.copy()

        self._monitoring = False
        if self._thread:
            self._thread.join(timeout=2.0)

        with self._lock:
            metrics = self._metrics.copy()
            self._metrics.clear()

        logger.debug("Performance monitoring stopped, collected %s metrics", len(metrics))
        return metrics

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                metrics = self._collect_metrics()
                with self._lock:
                    self._metrics.append(metrics)
            except Exception as exc:
                logger.warning("Failed to collect performance metrics: %s", exc)

            time.sleep(self.interval)

    def _collect_metrics(
        self,
    ) -> Dict[str, Union[float, int, str, None, Tuple[float, float, float]]]:
        """Collect current system performance metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            network = psutil.net_io_counters()

            return {
                "timestamp": time.time(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": memory.used / (1024**3),
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024**3),
                "disk_free_gb": disk.free / (1024**3),
                "network_bytes_sent": network.bytes_sent if network else 0,
                "network_bytes_recv": network.bytes_recv if network else 0,
                "load_average": os.getloadavg() if hasattr(os, "getloadavg") else None,
            }
        except Exception as exc:
            logger.warning("Error collecting metrics: %s", exc)
            return {"timestamp": time.time(), "error": str(exc)}


class ResourceOptimizer:
    """
    Optimize resource usage for better performance.

    Provides utilities to optimize CPU, memory, and I/O usage
    based on system capabilities and workload requirements.
    """

    @staticmethod
    def get_optimal_parallel_jobs(max_jobs: Optional[int] = None) -> int:
        """
        Determine optimal number of parallel jobs based on system resources.

        Args:
            max_jobs: Maximum number of jobs to allow (None = no limit)

        Returns:
            Optimal number of parallel jobs
        """
        try:
            cpu_count = multiprocessing.cpu_count()
            memory_gb = psutil.virtual_memory().total / (1024**3)

            # Base calculation on CPU cores, but consider memory
            optimal = min(cpu_count, int(memory_gb / 2))  # Assume 2GB per job

            # Apply limits
            if max_jobs:
                optimal = min(optimal, max_jobs)

            return max(1, optimal)

        except Exception:
            # Fallback to conservative defaults
            return max(1, multiprocessing.cpu_count() // 2)

    @staticmethod
    def optimize_process_priority() -> None:
        """Optimize current process priority for better performance."""
        try:
            import platform  # pylint: disable=import-outside-toplevel,reimported

            if platform.system() == "Windows":
                # On Windows, we can't easily change priority from user process
                pass
            else:
                # On Unix-like systems, try to set nice level
                if hasattr(os, "nice"):
                    os.nice(-5)  # Slightly higher priority
        except Exception:
            pass  # Ignore if we can't set priority

    @staticmethod
    def cleanup_memory() -> None:
        """Force garbage collection to free memory."""
        import gc  # pylint: disable=import-outside-toplevel,reimported

        gc.collect()

    @staticmethod
    def get_system_info() -> Dict[str, Union[int, float, str, None]]:
        """Get comprehensive system information for optimization decisions."""
        try:
            import platform  # pylint: disable=import-outside-toplevel,reimported

            return {
                "cpu_count": multiprocessing.cpu_count(),
                "cpu_freq": psutil.cpu_freq().current if psutil.cpu_freq() else None,
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "memory_available_gb": psutil.virtual_memory().available / (1024**3),
                "disk_total_gb": psutil.disk_usage("/").total / (1024**3),
                "disk_free_gb": psutil.disk_usage("/").free / (1024**3),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            }
        except Exception as exc:
            logger.warning("Failed to get system info: %s", exc)
            return {}


class ParallelExecutor:
    """
    Execute operations in parallel for improved performance.

    Provides a thread-safe way to execute multiple operations concurrently,
    with proper error handling and resource management.
    """

    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize parallel executor.

        Args:
            max_workers: Maximum number of worker threads (None = auto-detect)
        """
        if max_workers is None:
            max_workers = ResourceOptimizer.get_optimal_parallel_jobs()
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None

    def __enter__(self) -> "ParallelExecutor":
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    def execute_parallel(  # type: ignore[explicit-any]  # Callable[...] needed for generic task execution
        self, tasks: List[Tuple[Callable[..., T], Tuple[object, ...], Dict[str, object]]]
    ) -> List[Optional[T]]:
        """
        Execute tasks in parallel.

        Args:
            tasks: List of (function, args, kwargs) tuples

        Returns:
            List of results in the same order as tasks
        """
        if not self._executor:
            raise RuntimeError("ParallelExecutor must be used as context manager")

        # Submit all tasks
        futures: List[Future[T]] = []
        for func, args, kwargs in tasks:
            future = self._executor.submit(func, *args, **kwargs)
            futures.append(future)

        # Collect results in order
        results: List[Optional[T]] = []
        for future in futures:
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                logger.error("Task execution failed: %s", exc)
                results.append(None)  # Or raise exception based on requirements

        return results

    def map_parallel(self, func: Callable[[T], object], items: List[T]) -> List[Optional[object]]:
        """
        Apply function to all items in parallel.

        Args:
            func: Function to apply
            items: List of items to process

        Returns:
            List of results
        """
        if not self._executor:
            raise RuntimeError("ParallelExecutor must be used as context manager")

        futures = [self._executor.submit(func, item) for item in items]

        results = []
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                logger.error("Parallel map task failed: %s", exc)
                results.append(None)

        return results


# Global instances (module-level singleton)
_performance_monitor = None  # pylint: disable=invalid-name
_monitor_lock = threading.Lock()


def get_performance_monitor(interval: float = 1.0) -> PerformanceMonitor:
    """
    Get or create global performance monitor instance.

    Args:
        interval: Monitoring interval in seconds

    Returns:
        PerformanceMonitor instance
    """
    global _performance_monitor  # pylint: disable=global-statement

    if _performance_monitor is None:
        with _monitor_lock:
            if _performance_monitor is None:
                _performance_monitor = PerformanceMonitor(interval)

    return _performance_monitor


def optimize_system_resources() -> None:
    """
    Apply system-wide resource optimizations.

    This function applies various optimizations to improve overall system
    performance during testing operations.
    """
    try:
        # Optimize process priority
        ResourceOptimizer.optimize_process_priority()

        # Clean up memory
        ResourceOptimizer.cleanup_memory()

        # Log system information
        system_info = ResourceOptimizer.get_system_info()
        logger.info(
            "System optimization applied. CPU cores: %s, Memory: %.1fGB",
            system_info.get("cpu_count", "unknown"),
            system_info.get("memory_total_gb", 0.0),
        )

    except Exception as exc:
        logger.warning("System optimization failed: %s", exc)


def with_performance_monitoring(func: Callable[..., T]) -> Callable[..., T]:  # type: ignore[explicit-any]  # Callable[...] needed for generic decorator
    """
    Decorator to monitor performance during function execution.

    Args:
        func: Function to monitor

    Returns:
        Wrapped function that monitors performance
    """

    def wrapper(*args: object, **kwargs: object) -> T:
        monitor = get_performance_monitor()
        monitor.start_monitoring()

        try:
            result = func(*args, **kwargs)
            return result
        finally:
            metrics = monitor.stop_monitoring()
            if metrics:
                cpu_metrics = [
                    float(m["cpu_percent"])
                    for m in metrics
                    if "cpu_percent" in m and isinstance(m["cpu_percent"], (int, float))
                ]
                memory_metrics = [
                    float(m["memory_percent"])
                    for m in metrics
                    if "memory_percent" in m and isinstance(m["memory_percent"], (int, float))
                ]
                if cpu_metrics and memory_metrics:
                    avg_cpu = sum(cpu_metrics) / len(cpu_metrics)
                    avg_memory = sum(memory_metrics) / len(memory_metrics)
                    logger.info(
                        "Performance: CPU=%.2f%% Memory=%.2f%%",
                        avg_cpu,
                        avg_memory,
                    )

    return wrapper
