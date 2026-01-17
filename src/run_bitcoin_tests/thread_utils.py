"""
Thread safety utilities for concurrent operations.

This module provides thread-safe utilities for:
- File system operations with proper locking
- Resource cleanup with context managers
- Atomic operations for shared state
- Docker container management in concurrent environments
- Temporary directory management
- Resource tracking and automatic cleanup

Key Components:
- Thread-safe locks (RLock) for shared resources
- Context managers for atomic operations
- Resource trackers for automatic cleanup
- Emergency cleanup handlers for graceful shutdown
- Signal handling for clean termination

Thread Safety Guarantees:
- All file system operations are protected by locks
- Docker operations are serialized to prevent conflicts
- Shared state modifications are atomic
- Resource cleanup is thread-safe and comprehensive

Example Usage:
    from run_bitcoin_tests.thread_utils import atomic_directory_operation

    # Thread-safe directory creation
    with atomic_directory_operation(Path("my_dir"), "create_dir"):
        # Directory is guaranteed to exist here
        pass

    # Automatic cleanup on exit
    initialize_thread_safety()
"""

import atexit
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Generator, IO, List, Optional, Set, TypeVar

from .logging_config import get_logger

logger = get_logger(__name__)

# Type variable for resource tracking
T = TypeVar('T')

# Global locks for shared resources
_docker_lock = threading.RLock()
_file_system_lock = threading.RLock()
_temp_dir_lock = threading.RLock()

# Global state for tracking resources
_active_containers: Set[str] = set()
_temp_directories: Set[Path] = set()
_cleanup_handlers: List[Callable[[], None]] = []

# Thread-local storage for per-thread resources
_thread_local = threading.local()


def initialize_thread_safety() -> None:
    """
    Initialize thread safety mechanisms and cleanup handlers.

    This function should be called early in the application lifecycle to:
    - Register signal handlers for clean shutdown
    - Set up atexit handlers for emergency cleanup
    - Initialize global thread safety state

    Note:
        This function is idempotent and can be called multiple times safely.
    """
    # Register cleanup handlers
    atexit.register(_emergency_cleanup)

    # Set up signal handlers for clean shutdown (if needed)
    try:
        import signal  # pylint: disable=import-outside-toplevel

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    except (OSError, ValueError):
        # Signal handling not available on this platform
        pass

    logger.debug("Thread safety mechanisms initialized")


def _signal_handler(signum: int, frame: object) -> None:  # pylint: disable=unused-argument
    """Handle termination signals for clean shutdown."""
    logger.info("Received signal %s, initiating clean shutdown", signum)
    emergency_cleanup()
    os._exit(1)


def _emergency_cleanup() -> None:
    """Emergency cleanup function called at exit."""
    try:
        emergency_cleanup()
    except Exception:  # noqa: S110
        pass  # Silently ignore errors during shutdown


def emergency_cleanup() -> None:
    """Perform emergency cleanup of all resources."""
    # No need for global statement since we're not assigning to these variables
    with _docker_lock:
        for container_id in _active_containers.copy():
            try:
                _force_remove_container(container_id)
            except Exception as exc:
                logger.error("Failed to cleanup container %s: %s", container_id, exc)

        _active_containers.clear()

    with _temp_dir_lock:
        for temp_dir in _temp_directories.copy():
            try:
                _force_remove_temp_dir(temp_dir)
            except Exception as exc:
                logger.error("Failed to cleanup temp directory %s: %s", temp_dir, exc)

        _temp_directories.clear()

    # Run custom cleanup handlers
    for handler in _cleanup_handlers.copy():
        try:
            handler()
        except Exception as exc:
            logger.error("Error in cleanup handler: %s", exc)

    _cleanup_handlers.clear()


def _force_remove_container(container_id: str) -> None:
    """Force remove a Docker container."""
    try:
        import subprocess  # pylint: disable=import-outside-toplevel

        result = subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            logger.debug("Force removed container %s", container_id)
        else:
            logger.warning("Failed to remove container %s: %s", container_id, result.stderr)
    except Exception as exc:
        logger.error("Error removing container %s: %s", container_id, exc)


def _force_remove_temp_dir(temp_dir: Path) -> None:
    """Force remove a temporary directory."""
    try:
        import shutil  # pylint: disable=import-outside-toplevel

        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.debug("Removed temp directory %s", temp_dir)
    except Exception as exc:
        logger.error("Error removing temp directory %s: %s", temp_dir, exc)


@contextmanager
def docker_container_lock(container_name: Optional[str] = None) -> Generator[None, None, None]:
    """
    Context manager for thread-safe Docker container operations.

    This context manager ensures that Docker operations are serialized
    to prevent conflicts when multiple threads or processes might be
    working with containers simultaneously.

    Args:
        container_name: Optional container name to track for cleanup.
                       If provided, the container will be tracked globally
                       for emergency cleanup if needed.

    Yields:
        None (use as a context manager for synchronization only)

    Example:
        with docker_container_lock("my_container"):
            # Docker operations here are thread-safe
            run_docker_command(["docker", "build", "..."])
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
def file_system_lock(operation: str = "file_operation") -> Generator[None, None, None]:
    """
    Context manager for file system operations.

    Args:
        operation: Description of the operation for logging
    """
    logger.debug("Acquiring file system lock for: %s", operation)
    acquired_lock = _file_system_lock.acquire(timeout=30.0)
    if not acquired_lock:
        raise TimeoutError(f"Failed to acquire file system lock for {operation}")

    try:
        yield
    finally:
        _file_system_lock.release()
        logger.debug("Released file system lock for: %s", operation)


@contextmanager
def atomic_directory_operation(directory: Path, operation: str = "directory_op") -> Generator[Path, None, None]:
    """
    Context manager for atomic directory operations with thread safety.

    This function ensures that directory creation and operations are performed
    atomically and thread-safely. If the directory doesn't exist, it will be
    created. If it already exists, the operation proceeds normally.

    Args:
        directory: Directory path to operate on. Parent directories will be
                  created if they don't exist.
        operation: Human-readable description of the operation for logging
                  and error messages.

    Yields:
        Path: The directory path (guaranteed to exist within the context)

    Raises:
        OSError: If directory creation fails
        TimeoutError: If the file system lock cannot be acquired

    Example:
        with atomic_directory_operation(Path("build"), "create_build_dir"):
            # Directory ./build is guaranteed to exist here
            # and was created thread-safely
            pass
    """
    with file_system_lock(f"{operation} on {directory}"):

        # Ensure parent directories exist
        directory.parent.mkdir(parents=True, exist_ok=True)

        # Check if directory already exists
        if directory.exists():
            logger.debug("Directory %s already exists", directory)
            yield directory
            return

        # Create directory atomically
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug("Created directory %s for %s", directory, operation)
            yield directory
        except Exception as exc:
            logger.error("Failed to create directory %s: %s", directory, exc)
            raise


@contextmanager
def thread_safe_temp_dir(prefix: str = "bitcoin_tests_", suffix: str = "") -> Generator[Path, None, None]:
    """
    Create a thread-safe temporary directory with automatic cleanup.

    This function creates a temporary directory that is guaranteed to be
    unique and thread-safe. The directory is automatically cleaned up
    when exiting the context manager, even if exceptions occur.

    Args:
        prefix: Directory name prefix (default: "bitcoin_tests_")
        suffix: Directory name suffix (default: "")

    Yields:
        Path: Path to the temporary directory

    Example:
        with thread_safe_temp_dir("my_temp_") as temp_dir:
            # Use temp_dir for temporary files
            temp_file = temp_dir / "data.txt"
            temp_file.write_text("temporary data")
            # Directory is automatically cleaned up on exit
    """
    temp_dir = None

    with _temp_dir_lock:
        try:
            # Create temporary directory
            temp_dir = Path(tempfile.mkdtemp(prefix=prefix, suffix=suffix))
            _temp_directories.add(temp_dir)
            logger.debug("Created thread-safe temp directory: %s", temp_dir)

            yield temp_dir

        except Exception as exc:
            logger.error("Failed to create temp directory: %s", exc)
            if temp_dir and temp_dir.exists():
                try:
                    import shutil  # pylint: disable=import-outside-toplevel

                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            raise
        finally:
            if temp_dir:
                _temp_directories.discard(temp_dir)
                if temp_dir.exists():
                    try:
                        import shutil  # pylint: disable=import-outside-toplevel

                        shutil.rmtree(temp_dir)
                        logger.debug("Cleaned up temp directory: %s", temp_dir)
                    except Exception as exc:
                        logger.warning("Failed to cleanup temp directory %s: %s", temp_dir, exc)


@contextmanager
def exclusive_file_operation(file_path: Path, mode: str = "r", operation: str = "file_access") -> Generator[IO[str], None, None]:
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
            with open(file_path, mode, encoding="utf-8") as file_obj:
                logger.debug("Opened file %s for %s", file_path, operation)
                yield file_obj
        except Exception as exc:
            logger.error("Error in file operation %s on %s: %s", operation, file_path, exc)
            raise


_cleanup_handler_lock = threading.Lock()


def register_cleanup_handler(handler: Callable[[], None]) -> None:
    """
    Register a cleanup handler to be called on exit.

    Args:
        handler: Callable to execute during cleanup
    """
    with _cleanup_handler_lock:
        _cleanup_handlers.append(handler)
        logger.debug("Registered cleanup handler")


def unregister_cleanup_handler(handler: Callable[[], None]) -> None:
    """
    Unregister a cleanup handler.

    Args:
        handler: Handler to remove
    """
    with _cleanup_handler_lock:
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

    def reset(self) -> None:
        """Reset counter to zero."""
        with self._lock:
            self._value = 0


class ResourceTracker:
    """
    Thread-safe resource tracker for monitoring and managing system resources.

    This class provides a centralized way to track resources that need
    cleanup or management across the application. Resources can be registered
    with automatic cleanup capabilities.

    All operations are thread-safe and can be called concurrently from
    multiple threads.

    Example:
        tracker = ResourceTracker()
        tracker.register_resource("my_file", open("file.txt", "w"))

        # Later, cleanup all resources
        tracker.cleanup_all_resources()
    """

    def __init__(self) -> None:
        """Initialize the resource tracker."""
        self._resources: Dict[str, object] = {}
        self._lock = threading.Lock()

    def register_resource(self, name: str, resource: object) -> None:
        """
        Register a resource for tracking and potential cleanup.

        Args:
            name: Unique identifier for the resource
            resource: The resource object to track
        """
        with self._lock:
            self._resources[name] = resource
            logger.debug("Registered resource: %s", name)

    def unregister_resource(self, name: str) -> None:
        """
        Unregister a tracked resource.

        Args:
            name: Resource identifier to remove
        """
        with self._lock:
            if name in self._resources:
                del self._resources[name]
                logger.debug("Unregistered resource: %s", name)

    def get_resource(self, name: str) -> Optional[object]:
        """
        Get a tracked resource by name.

        Args:
            name: Resource identifier to retrieve

        Returns:
            The resource object, or None if not found
        """
        with self._lock:
            return self._resources.get(name)

    def list_resources(self) -> List[str]:
        """
        List all tracked resource names.

        Returns:
            List of resource identifier strings
        """
        with self._lock:
            return list(self._resources.keys())

    def cleanup_all_resources(self) -> None:
        """
        Cleanup all tracked resources.

        This method attempts to call cleanup() or close() methods on
        tracked resources if they exist. Errors during cleanup are
        logged but don't prevent other resources from being cleaned up.
        """
        with self._lock:
            for name, resource in self._resources.items():
                try:
                    if hasattr(resource, "cleanup") and callable(resource.cleanup):
                        resource.cleanup()
                    elif hasattr(resource, "close") and callable(resource.close):
                        resource.close()
                    logger.debug("Cleaned up resource: %s", name)
                except Exception as exc:
                    logger.error("Error cleaning up resource %s: %s", name, exc)

            self._resources.clear()


# Global instances
resource_tracker = ResourceTracker()
operation_counter = ThreadSafeCounter()
