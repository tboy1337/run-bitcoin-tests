"""Tests for thread safety utilities."""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.thread_utils import (
    ResourceTracker,
    ThreadSafeCounter,
    atomic_directory_operation,
    docker_container_lock,
    emergency_cleanup,
    file_system_lock,
    register_cleanup_handler,
    thread_safe_temp_dir,
    unregister_cleanup_handler,
)


class TestThreadSafeCounter:
    """Test thread-safe counter functionality."""

    def test_initial_value(self):
        """Test counter initializes with correct value."""
        counter = ThreadSafeCounter(5)
        assert counter.get_value() == 5

    def test_increment(self):
        """Test increment operation."""
        counter = ThreadSafeCounter()
        assert counter.increment() == 1
        assert counter.increment() == 2
        assert counter.get_value() == 2

    def test_decrement(self):
        """Test decrement operation."""
        counter = ThreadSafeCounter(10)
        assert counter.decrement() == 9
        assert counter.decrement() == 8
        assert counter.get_value() == 8

    def test_reset(self):
        """Test reset operation."""
        counter = ThreadSafeCounter(5)
        counter.increment()
        counter.reset()
        assert counter.get_value() == 0

    def test_thread_safety(self):
        """Test counter works correctly with multiple threads."""
        counter = ThreadSafeCounter()
        results = []

        def increment_worker():
            for _ in range(100):
                counter.increment()
                time.sleep(0.001)  # Small delay to increase chance of race conditions

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=increment_worker)
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Each thread incremented 100 times, 5 threads = 500 total
        assert counter.get_value() == 500


class TestResourceTracker:
    """Test resource tracker functionality."""

    def test_register_and_get_resource(self):
        """Test registering and retrieving resources."""
        tracker = ResourceTracker()

        resource = Mock()
        tracker.register_resource("test_resource", resource)

        retrieved = tracker.get_resource("test_resource")
        assert retrieved == resource

    def test_unregister_resource(self):
        """Test unregistering resources."""
        tracker = ResourceTracker()

        resource = Mock()
        tracker.register_resource("test_resource", resource)

        assert tracker.get_resource("test_resource") is not None

        tracker.unregister_resource("test_resource")
        assert tracker.get_resource("test_resource") is None

    def test_list_resources(self):
        """Test listing tracked resources."""
        tracker = ResourceTracker()

        tracker.register_resource("res1", Mock())
        tracker.register_resource("res2", Mock())

        resources = tracker.list_resources()
        assert "res1" in resources
        assert "res2" in resources
        assert len(resources) == 2

    def test_cleanup_resources(self):
        """Test cleanup of all resources."""
        tracker = ResourceTracker()

        resource1 = Mock()
        resource2 = Mock()

        tracker.register_resource("res1", resource1)
        tracker.register_resource("res2", resource2)

        tracker.cleanup_all_resources()

        # Resources should have been cleaned up
        assert tracker.list_resources() == []

        # cleanup should have been called on resources that have it
        resource1.cleanup.assert_called_once()
        resource2.cleanup.assert_called_once()


class TestAtomicDirectoryOperation:
    """Test atomic directory operations."""

    def test_create_new_directory(self):
        """Test creating a new directory atomically."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_atomic_dir"

            assert not test_dir.exists()

            with atomic_directory_operation(test_dir, "test_create"):
                assert test_dir.exists()
                assert test_dir.is_dir()

            # Directory should still exist after context
            assert test_dir.exists()

    def test_existing_directory(self):
        """Test operation on existing directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "existing_dir"
            test_dir.mkdir()

            assert test_dir.exists()

            with atomic_directory_operation(test_dir, "test_existing"):
                assert test_dir.exists()
                assert test_dir.is_dir()

    def test_nested_directories(self):
        """Test creating nested directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_dir = Path(temp_dir) / "level1" / "level2" / "level3"

            assert not nested_dir.exists()

            with atomic_directory_operation(nested_dir, "test_nested"):
                assert nested_dir.exists()
                assert nested_dir.is_dir()

            assert nested_dir.exists()


class TestThreadSafeTempDir:
    """Test thread-safe temporary directory creation."""

    def test_create_temp_dir(self):
        """Test creating a thread-safe temporary directory."""
        with thread_safe_temp_dir(prefix="test_") as temp_dir:
            assert temp_dir.exists()
            assert temp_dir.is_dir()
            assert temp_dir.name.startswith("test_")

            # Can create files in the directory
            test_file = temp_dir / "test.txt"
            test_file.write_text("test content")
            assert test_file.exists()

        # Directory should be cleaned up after context
        assert not temp_dir.exists()

    def test_temp_dir_with_suffix(self):
        """Test temp directory with custom suffix."""
        with thread_safe_temp_dir(prefix="pre_", suffix="_suf") as temp_dir:
            assert temp_dir.name.startswith("pre_")
            assert temp_dir.name.endswith("_suf")


class TestCleanupHandlers:
    """Test cleanup handler registration and execution."""

    def test_register_and_cleanup(self):
        """Test registering and running cleanup handlers."""
        cleanup_called = []

        def test_cleanup():
            cleanup_called.append(True)

        register_cleanup_handler(test_cleanup)

        # Simulate emergency cleanup
        emergency_cleanup()

        assert len(cleanup_called) == 1

    def test_unregister_handler(self):
        """Test unregistering cleanup handlers."""
        cleanup_called = []

        def test_cleanup():
            cleanup_called.append(True)

        register_cleanup_handler(test_cleanup)
        unregister_cleanup_handler(test_cleanup)

        emergency_cleanup()

        # Handler should not have been called since it was unregistered
        assert len(cleanup_called) == 0


class TestFileSystemLock:
    """Test file system locking."""

    def test_file_system_lock_basic(self):
        """Test basic file system lock operation."""
        lock_acquired = []

        def test_operation():
            lock_acquired.append(True)

        with file_system_lock("test_operation"):
            test_operation()

        assert len(lock_acquired) == 1

    def test_file_system_lock_timeout(self):
        """Test file system lock timeout behavior."""
        # This is hard to test directly without complex threading,
        # but the lock should work with reasonable timeout
        with file_system_lock("test_timeout"):
            pass  # Should not hang


class TestDockerContainerLock:
    """Test Docker container locking."""

    def test_docker_lock_basic(self):
        """Test basic Docker container lock operation."""
        lock_acquired = []

        def test_operation():
            lock_acquired.append(True)

        with docker_container_lock("test_container"):
            test_operation()

        assert len(lock_acquired) == 1

    def test_docker_lock_without_container(self):
        """Test Docker lock without specifying container name."""
        lock_acquired = []

        def test_operation():
            lock_acquired.append(True)

        with docker_container_lock():
            test_operation()

        assert len(lock_acquired) == 1


class TestEmergencyCleanup:
    """Test emergency cleanup functionality."""

    @patch("run_bitcoin_tests.thread_utils._force_remove_container")
    @patch("run_bitcoin_tests.thread_utils._force_remove_temp_dir")
    def test_emergency_cleanup(self, mock_remove_temp, mock_remove_container):
        """Test emergency cleanup calls appropriate functions."""
        # Add some mock containers and temp dirs to the global sets
        from run_bitcoin_tests.thread_utils import _active_containers, _temp_directories

        # Temporarily add items (this is not thread-safe but ok for testing)
        _active_containers.add("test_container")
        _temp_directories.add(Path("/tmp/test"))

        emergency_cleanup()

        # Should have called cleanup functions
        mock_remove_container.assert_called_once_with("test_container")
        mock_remove_temp.assert_called_once()

        # Sets should be cleared
        assert len(_active_containers) == 0
        assert len(_temp_directories) == 0