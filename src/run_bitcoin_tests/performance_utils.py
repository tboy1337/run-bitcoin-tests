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

import gc
import logging
import multiprocessing
import os
import platform
import psutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

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
        self._metrics: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def start_monitoring(self) -> None:
        """Start performance monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.debug("Performance monitoring started")

    def stop_monitoring(self) -> List[Dict[str, Any]]:
        """Stop monitoring and return collected metrics."""
        if not self._monitoring:
            return self._metrics.copy()

        self._monitoring = False
        if self._thread:
            self._thread.join(timeout=2.0)

        with self._lock:
            metrics = self._metrics.copy()
            self._metrics.clear()

        logger.debug(f"Performance monitoring stopped, collected {len(metrics)} metrics")
        return metrics

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                metrics = self._collect_metrics()
                with self._lock:
                    self._metrics.append(metrics)
            except Exception as e:
                logger.warning(f"Failed to collect performance metrics: {e}")

            time.sleep(self.interval)

    def _collect_metrics(self) -> Dict[str, Any]:
        """Collect current system performance metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()

            return {
                'timestamp': time.time(),
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024**3),
                'memory_available_gb': memory.available / (1024**3),
                'disk_percent': disk.percent,
                'disk_used_gb': disk.used / (1024**3),
                'disk_free_gb': disk.free / (1024**3),
                'network_bytes_sent': network.bytes_sent if network else 0,
                'network_bytes_recv': network.bytes_recv if network else 0,
                'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None
            }
        except Exception as e:
            logger.warning(f"Error collecting metrics: {e}")
            return {'timestamp': time.time(), 'error': str(e)}


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
            import platform
            if platform.system() == 'Windows':
                # On Windows, we can't easily change priority from user process
                pass
            else:
                # On Unix-like systems, try to set nice level
                os.nice(-5)  # Slightly higher priority
        except Exception:
            pass  # Ignore if we can't set priority

    @staticmethod
    def cleanup_memory() -> None:
        """Force garbage collection to free memory."""
        import gc
        gc.collect()

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Get comprehensive system information for optimization decisions."""
        try:
            return {
                'cpu_count': multiprocessing.cpu_count(),
                'cpu_freq': psutil.cpu_freq().current if psutil.cpu_freq() else None,
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'memory_available_gb': psutil.virtual_memory().available / (1024**3),
                'disk_total_gb': psutil.disk_usage('/').total / (1024**3),
                'disk_free_gb': psutil.disk_usage('/').free / (1024**3),
                'platform': platform.platform(),
                'python_version': platform.python_version()
            }
        except Exception as e:
            logger.warning(f"Failed to get system info: {e}")
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

    def __enter__(self):
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._executor:
            self._executor.shutdown(wait=True)

    def execute_parallel(self, tasks: List[Tuple[Callable, Tuple, Dict]]) -> List[Any]:
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
        futures = []
        for func, args, kwargs in tasks:
            future = self._executor.submit(func, *args, **kwargs)
            futures.append(future)

        # Collect results in order
        results = []
        for future in futures:
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Task execution failed: {e}")
                results.append(None)  # Or raise exception based on requirements

        return results

    def map_parallel(self, func: Callable, items: List[Any]) -> List[Any]:
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
            except Exception as e:
                logger.error(f"Parallel map task failed: {e}")
                results.append(None)

        return results


# Global instances
_performance_monitor = None
_monitor_lock = threading.Lock()


def get_performance_monitor(interval: float = 1.0) -> PerformanceMonitor:
    """
    Get or create global performance monitor instance.

    Args:
        interval: Monitoring interval in seconds

    Returns:
        PerformanceMonitor instance
    """
    global _performance_monitor

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
        logger.info(f"System optimization applied. CPU cores: {system_info.get('cpu_count', 'unknown')}, "
                   f"Memory: {system_info.get('memory_total_gb', 'unknown'):.1f}GB")

    except Exception as e:
        logger.warning(f"System optimization failed: {e}")


def with_performance_monitoring(func: Callable) -> Callable:
    """
    Decorator to monitor performance during function execution.

    Args:
        func: Function to monitor

    Returns:
        Wrapped function that monitors performance
    """
    def wrapper(*args, **kwargs):
        monitor = get_performance_monitor()
        monitor.start_monitoring()

        try:
            result = func(*args, **kwargs)
            return result
        finally:
            metrics = monitor.stop_monitoring()
            if metrics:
                avg_cpu = sum(m['cpu_percent'] for m in metrics if 'cpu_percent' in m) / len(metrics)
                avg_memory = sum(m['memory_percent'] for m in metrics if 'memory_percent' in m) / len(metrics)
                logger.info(".2f")

    return wrapper