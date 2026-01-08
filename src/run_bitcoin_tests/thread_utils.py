"""
Thread safety utilities for concurrent operations.

This module provides thread-safe utilities for:
- File system operations with proper locking
- Resource cleanup with context managers
- Atomic operations for shared state
- Docker container management in concurrent environments
"""

import atexit
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .logging_config import get_logger

logger = get_logger(__name__)

# Global locks for shared resources
_docker_lock = threading.RLock()
_file_system_lock = threading.RLock()
_temp_dir_lock = threading.RLock()

# Global state for tracking resources
_active_containers: Set[str] = set()
_temp_directories: Set[Path] = set()
_cleanup_handlers: List[callable] = []

# Thread-local storage for per-thread resources
_thread_local = threading.local()


def initialize_thread_safety():
    """Initialize thread safety mechanisms."""
    # Register cleanup handlers
    atexit.register(_emergency_cleanup)

    # Set up signal handlers for clean shutdown (if needed)
    try:
        import signal
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    except (OSError, ValueError):
        # Signal handling not available on this platform
        pass

    logger.debug("Thread safety mechanisms initialized")


def _signal_handler(signum, frame):
    """Handle termination signals for clean shutdown."""
    logger.info(f"Received signal {signum}, initiating clean shutdown")
    emergency_cleanup()
    os._exit(1)


def _emergency_cleanup():
    """Emergency cleanup function called at exit."""
    logger.info("Performing emergency cleanup")
    try:
        emergency_cleanup()
    except Exception as e:
        logger.error(f"Error during emergency cleanup: {e}")


def emergency_cleanup():
    """Perform emergency cleanup of all resources."""
    global _active_containers, _temp_directories

    with _docker_lock:
        for container_id in _active_containers.copy():
            try:
                _force_remove_container(container_id)
            except Exception as e:
                logger.error(f"Failed to cleanup container {container_id}: {e}")

        _active_containers.clear()

    with _temp_dir_lock:
        for temp_dir in _temp_directories.copy():
            try:
                _force_remove_temp_dir(temp_dir)
            except Exception as e:
                logger.error(f"Failed to cleanup temp directory {temp_dir}: {e}")

        _temp_directories.clear()

    # Run custom cleanup handlers
    for handler in _cleanup_handlers.copy():
        try:
            handler()
        except Exception as e:
            logger.error(f"Error in cleanup handler: {e}")

    _cleanup_handlers.clear()


def _force_remove_container(container_id: str):
    """Force remove a Docker container."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            logger.debug(f"Force removed container {container_id}")
        else:
            logger.warning(f"Failed to remove container {container_id}: {result.stderr}")
    except Exception as e:
        logger.error(f"Error removing container {container_id}: {e}")


def _force_remove_temp_dir(temp_dir: Path):
    """Force remove a temporary directory."""
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.debug(f"Removed temp directory {temp_dir}")
    except Exception as e:
        logger.error(f"Error removing temp directory {temp_dir}: {e}")


@contextmanager
def docker_container_lock(container_name: Optional[str] = None):
    """
    Context manager for Docker container operations.

    Args:
        container_name: Optional container name to track
    """
    acquired_lock = _docker_lock.acquire(timeout=30.0)
    if not acquired_lock:
        raise TimeoutError("Failed to acquire Docker lock within timeout")

    try:
        if container_name:
            _active_containers.add(container_name)
        yield
    finally:
        if container_name:
            _active_containers.discard(container_name)
        _docker_lock.release()


@contextmanager
def file_system_lock(operation: str = "file_operation"):
    """
    Context manager for file system operations.

    Args:
        operation: Description of the operation for logging
    """
    logger.debug(f"Acquiring file system lock for: {operation}")
    acquired_lock = _file_system_lock.acquire(timeout=30.0)
    if not acquired_lock:
        raise TimeoutError(f"Failed to acquire file system lock for {operation}")

    try:
        yield
    finally:
        _file_system_lock.release()
        logger.debug(f"Released file system lock for: {operation}")


@contextmanager
def atomic_directory_operation(directory: Path, operation: str = "directory_op"):
    """
    Context manager for atomic directory operations.

    Args:
        directory: Directory path to operate on
        operation: Description of the operation
    """
    with file_system_lock(f"{operation} on {directory}"):

        # Ensure parent directories exist
        directory.parent.mkdir(parents=True, exist_ok=True)

        # Check if directory already exists
        if directory.exists():
            logger.debug(f"Directory {directory} already exists")
            yield directory
            return

        # Create directory atomically
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory {directory} for {operation}")
            yield directory
        except Exception as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            raise


@contextmanager
def thread_safe_temp_dir(prefix: str = "bitcoin_tests_", suffix: str = ""):
    """
    Create a thread-safe temporary directory.

    Args:
        prefix: Directory name prefix
        suffix: Directory name suffix

    Yields:
        Path to the temporary directory
    """
    temp_dir = None

    with _temp_dir_lock:
        try:
            # Create temporary directory
            temp_dir = Path(tempfile.mkdtemp(prefix=prefix, suffix=suffix))
            _temp_directories.add(temp_dir)
            logger.debug(f"Created thread-safe temp directory: {temp_dir}")

            yield temp_dir

        except Exception as e:
            logger.error(f"Failed to create temp directory: {e}")
            if temp_dir and temp_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            raise
        finally:
            if temp_dir:
                _temp_directories.discard(temp_dir)
                if temp_dir.exists():
                    try:
                        import shutil
                        shutil.rmtree(temp_dir)
                        logger.debug(f"Cleaned up temp directory: {temp_dir}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")


@contextmanager
def exclusive_file_operation(file_path: Path, mode: str = "r", operation: str = "file_access"):
    """
    Context manager for exclusive file operations.

    Args:
        file_path: Path to the file
        mode: File open mode
        operation: Description of the operation

    Yields:
        Opened file handle
    """
    with file_system_lock(f"{operation} on {file_path}"):
        try:
            with open(file_path, mode, encoding='utf-8') as f:
                logger.debug(f"Opened file {file_path} for {operation}")
                yield f
        except Exception as e:
            logger.error(f"Error in file operation {operation} on {file_path}: {e}")
            raise


def register_cleanup_handler(handler: callable):
    """
    Register a cleanup handler to be called on exit.

    Args:
        handler: Callable to execute during cleanup
    """
    with threading.Lock():
        _cleanup_handlers.append(handler)
        logger.debug("Registered cleanup handler")


def unregister_cleanup_handler(handler: callable):
    """
    Unregister a cleanup handler.

    Args:
        handler: Handler to remove
    """
    with threading.Lock():
        try:
            _cleanup_handlers.remove(handler)
            logger.debug("Unregistered cleanup handler")
        except ValueError:
            logger.warning("Attempted to unregister non-existent cleanup handler")


class ThreadSafeCounter:
    """Thread-safe counter for tracking concurrent operations."""

    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.Lock()

    def increment(self) -> int:
        """Increment counter and return new value."""
        with self._lock:
            self._value += 1
            return self._value

    def decrement(self) -> int:
        """Decrement counter and return new value."""
        with self._lock:
            self._value -= 1
            return self._value

    def get_value(self) -> int:
        """Get current counter value."""
        with self._lock:
            return self._value

    def reset(self):
        """Reset counter to zero."""
        with self._lock:
            self._value = 0


class ResourceTracker:
    """Thread-safe resource tracker for monitoring system resources."""

    def __init__(self):
        self._resources: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register_resource(self, name: str, resource: Any):
        """Register a resource for tracking."""
        with self._lock:
            self._resources[name] = resource
            logger.debug(f"Registered resource: {name}")

    def unregister_resource(self, name: str):
        """Unregister a tracked resource."""
        with self._lock:
            if name in self._resources:
                del self._resources[name]
                logger.debug(f"Unregistered resource: {name}")

    def get_resource(self, name: str) -> Optional[Any]:
        """Get a tracked resource."""
        with self._lock:
            return self._resources.get(name)

    def list_resources(self) -> List[str]:
        """List all tracked resource names."""
        with self._lock:
            return list(self._resources.keys())

    def cleanup_all_resources(self):
        """Cleanup all tracked resources."""
        with self._lock:
            for name, resource in self._resources.items():
                try:
                    if hasattr(resource, 'cleanup') and callable(resource.cleanup):
                        resource.cleanup()
                    elif hasattr(resource, 'close') and callable(resource.close):
                        resource.close()
                    logger.debug(f"Cleaned up resource: {name}")
                except Exception as e:
                    logger.error(f"Error cleaning up resource {name}: {e}")

            self._resources.clear()


# Global instances
resource_tracker = ResourceTracker()
operation_counter = ThreadSafeCounter()