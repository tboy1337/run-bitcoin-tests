"""
Tests for GitCache functionality in network_utils.py.

This module contains comprehensive tests for the Git repository caching
system that improves performance by avoiding repeated downloads.
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from run_bitcoin_tests.network_utils import GitCache, get_git_cache


class TestGitCache:
    """Test cases for GitCache class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache = GitCache(cache_dir=str(self.temp_dir), max_cache_size_gb=1.0)

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test GitCache initialization."""
        assert self.cache.cache_dir == self.temp_dir
        assert self.cache.max_cache_size_gb == 1.0
        # Metadata file may or may not exist initially
        assert self.cache._metadata == {}

    def test_get_repo_hash(self):
        """Test repository hash generation."""
        repo_url = "https://github.com/bitcoin/bitcoin"
        branch = "master"

        hash1 = self.cache._get_repo_hash(repo_url, branch)
        hash2 = self.cache._get_repo_hash(repo_url, branch)

        # Same inputs should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 16  # 16 hex chars

        # Different inputs should produce different hashes
        hash3 = self.cache._get_repo_hash(repo_url, "develop")
        assert hash1 != hash3

    def test_get_cache_path(self):
        """Test cache path generation."""
        repo_hash = "abcd1234abcd1234"
        cache_path = self.cache._get_cache_path(repo_hash)

        assert cache_path == self.cache.cache_dir / repo_hash
        assert str(cache_path).endswith(repo_hash)

    def test_load_save_metadata(self):
        """Test metadata loading and saving."""
        # Initially empty
        assert self.cache._metadata == {}

        # Add some metadata
        test_metadata = {
            'hash1': {'repo_url': 'url1', 'branch': 'branch1', 'cached_at': time.time()},
            'hash2': {'repo_url': 'url2', 'branch': 'branch2', 'cached_at': time.time()}
        }
        self.cache._metadata = test_metadata
        self.cache._save_metadata()

        # Create new cache instance to test loading
        new_cache = GitCache(cache_dir=str(self.temp_dir))
        assert new_cache._metadata == test_metadata

    def test_get_cached_repo_not_found(self):
        """Test getting cached repo when none exists."""
        result = self.cache.get_cached_repo("https://github.com/test/repo", "main")
        assert result is None

    def test_get_cached_repo_invalid(self):
        """Test getting cached repo that's invalid."""
        repo_url = "https://github.com/test/repo"
        branch = "main"
        repo_hash = self.cache._get_repo_hash(repo_url, branch)
        cache_path = self.cache._get_cache_path(repo_hash)

        # Create cache directory but no .git
        cache_path.mkdir()
        self.cache._metadata[repo_hash] = {
            'repo_url': repo_url,
            'branch': branch,
            'cached_at': time.time()
        }
        self.cache._save_metadata()

        result = self.cache.get_cached_repo(repo_url, branch)
        assert result is None

    @patch('run_bitcoin_tests.network_utils.subprocess.run')
    def test_get_cached_repo_valid(self, mock_run):
        """Test getting valid cached repository."""
        # Mock successful git operations
        mock_run.return_value = Mock(returncode=0)

        repo_url = "https://github.com/test/repo"
        branch = "main"
        repo_hash = self.cache._get_repo_hash(repo_url, branch)
        cache_path = self.cache._get_cache_path(repo_hash)

        # Create valid cache structure
        cache_path.mkdir()
        (cache_path / ".git").mkdir()

        self.cache._metadata[repo_hash] = {
            'repo_url': repo_url,
            'branch': branch,
            'cached_at': time.time()
        }
        self.cache._save_metadata()

        result = self.cache.get_cached_repo(repo_url, branch)
        assert result == cache_path

    @patch('run_bitcoin_tests.network_utils.shutil.copytree')
    def test_cache_repo_success(self, mock_copytree):
        """Test successful repository caching."""
        repo_url = "https://github.com/test/repo"
        branch = "main"
        source_path = self.temp_dir / "source"
        source_path.mkdir()

        # Create a mock .git directory
        (source_path / ".git").mkdir()

        result = self.cache.cache_repo(repo_url, branch, source_path)
        assert result is True

        # Check that metadata was updated
        repo_hash = self.cache._get_repo_hash(repo_url, branch)
        assert repo_hash in self.cache._metadata

        metadata = self.cache._metadata[repo_hash]
        assert metadata['repo_url'] == repo_url
        assert metadata['branch'] == branch
        assert 'cached_at' in metadata

    def test_cache_repo_failure(self):
        """Test repository caching failure."""
        # Try to cache non-existent source
        source_path = self.temp_dir / "nonexistent"
        result = self.cache.cache_repo("https://github.com/test/repo", "main", source_path)
        assert result is False

    def test_cleanup_old_cache(self):
        """Test cache cleanup when size limit exceeded."""
        # Create some fake cache entries
        for i in range(3):
            repo_hash = f"hash{i:016d}"
            cache_path = self.cache._get_cache_path(repo_hash)
            cache_path.mkdir()

            # Create a small fake file
            fake_file = cache_path / "fake_file"
            with open(fake_file, 'w') as f:
                f.write("x" * 1024)  # 1KB per repo

            self.cache._metadata[repo_hash] = {
                'repo_url': f'url{i}',
                'branch': f'branch{i}',
                'cached_at': time.time() - (i * 3600)  # Different ages
            }

        self.cache._save_metadata()

        # Set a very small cache limit to force cleanup
        original_limit = self.cache.max_cache_size_gb
        self.cache.max_cache_size_gb = 0.000001  # ~1KB limit

        try:
            # Trigger cleanup
            self.cache._cleanup_old_cache()

            # Should have cleaned up some entries (at least the oldest)
            remaining_entries = len([d for d in self.cache.cache_dir.iterdir()
                                   if d.is_dir() and d != self.cache.cache_metadata_file.parent])
            assert remaining_entries < 3  # Should have removed at least one
        finally:
            self.cache.max_cache_size_gb = original_limit

    def test_clear_cache(self):
        """Test cache clearing."""
        # Add some fake entries
        for i in range(3):
            repo_hash = f"hash{i:016d}"
            cache_path = self.cache._get_cache_path(repo_hash)
            cache_path.mkdir()

            self.cache._metadata[repo_hash] = {
                'repo_url': f'url{i}',
                'branch': f'branch{i}',
                'cached_at': time.time()
            }

        self.cache._save_metadata()

        # Verify entries exist
        assert len(self.cache._metadata) == 3

        # Clear cache
        self.cache.clear_cache()

        # Verify cache is cleared
        assert len(self.cache._metadata) == 0
        remaining_dirs = [d for d in self.cache.cache_dir.iterdir()
                         if d.is_dir() and d != self.cache.cache_metadata_file.parent]
        assert len(remaining_dirs) == 0


class TestGitCacheSingleton:
    """Test GitCache singleton functionality."""

    def test_get_git_cache_singleton(self):
        """Test that get_git_cache returns singleton instances."""
        # Clear any existing instance
        import run_bitcoin_tests.network_utils as network_utils
        network_utils._git_cache = None

        cache1 = get_git_cache()
        cache2 = get_git_cache()

        assert cache1 is cache2
        assert isinstance(cache1, GitCache)

    def test_get_git_cache_custom_params(self):
        """Test get_git_cache with custom parameters."""
        # Since get_git_cache is a singleton, we need to test it differently
        # The first call with custom params should create the cache with those params
        # But subsequent calls return the same instance
        with tempfile.TemporaryDirectory() as temp_dir:
            # Reset the global cache for this test
            import run_bitcoin_tests.network_utils as nu
            nu._git_cache = None

            cache = get_git_cache(cache_dir=temp_dir, max_cache_size_gb=2.0)

            assert cache.cache_dir == Path(temp_dir)
            assert cache.max_cache_size_gb == 2.0


class TestGitCacheIntegration:
    """Integration tests for GitCache with real filesystem operations."""

    def setup_method(self):
        """Set up integration test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache = GitCache(cache_dir=str(self.temp_dir / "cache"), max_cache_size_gb=1.0)

        # Create a fake git repository
        self.source_repo = self.temp_dir / "source_repo"
        self.source_repo.mkdir()
        (self.source_repo / ".git").mkdir()
        (self.source_repo / "README.md").write_text("# Test Repo")

        # Initialize git repo and create main branch
        import subprocess
        subprocess.run(["git", "init"], cwd=self.source_repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.source_repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.source_repo, check=True, capture_output=True)
        subprocess.run(["git", "add", "README.md"], cwd=self.source_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.source_repo, check=True, capture_output=True)

    def teardown_method(self):
        """Clean up integration test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_cache_workflow(self):
        """Test complete cache workflow: miss -> cache -> hit."""
        repo_url = "https://github.com/test/repo"
        branch = "main"

        # First access - cache miss
        result1 = self.cache.get_cached_repo(repo_url, branch)
        assert result1 is None

        # Cache the repository
        success = self.cache.cache_repo(repo_url, branch, self.source_repo)
        assert success

        # Second access - cache hit
        result2 = self.cache.get_cached_repo(repo_url, branch)
        assert result2 is not None
        assert result2.exists()
        assert (result2 / "README.md").exists()

    def test_cache_validation(self):
        """Test that cached repositories are properly validated."""
        repo_url = "https://github.com/test/repo"
        branch = "main"

        # Cache the repository
        self.cache.cache_repo(repo_url, branch, self.source_repo)

        # Verify it can be retrieved
        cached = self.cache.get_cached_repo(repo_url, branch)
        assert cached is not None

        # Simulate corrupted cache (remove .git directory)
        shutil.rmtree(cached / ".git")

        # Should no longer be retrievable
        result = self.cache.get_cached_repo(repo_url, branch)
        assert result is None

    def test_different_branches(self):
        """Test caching different branches separately."""
        repo_url = "https://github.com/test/repo"

        # Cache master branch
        self.cache.cache_repo(repo_url, "master", self.source_repo)
        master_cache = self.cache.get_cached_repo(repo_url, "master")
        assert master_cache is not None

        # Create a different source for develop branch
        develop_source = self.temp_dir / "develop_repo"
        shutil.copytree(self.source_repo, develop_source)
        (develop_source / "DEVELOP.md").write_text("# Develop Branch")

        # Cache develop branch
        self.cache.cache_repo(repo_url, "develop", develop_source)
        develop_cache = self.cache.get_cached_repo(repo_url, "develop")
        assert develop_cache is not None

        # They should be different cache entries
        assert master_cache != develop_cache

        # Both should be retrievable
        assert self.cache.get_cached_repo(repo_url, "master") == master_cache
        assert self.cache.get_cached_repo(repo_url, "develop") == develop_cache


class TestGitCacheErrorHandling:
    """Test error handling in GitCache."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache = GitCache(cache_dir=str(self.temp_dir), max_cache_size_gb=1.0)

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_corrupted_metadata_file(self):
        """Test handling of corrupted metadata file."""
        # Write invalid JSON to metadata file
        with open(self.cache.cache_metadata_file, 'w') as f:
            f.write("invalid json content")

        # Should handle gracefully and return empty metadata
        new_cache = GitCache(cache_dir=str(self.temp_dir))
        assert new_cache._metadata == {}

    def test_metadata_save_failure(self):
        """Test handling of metadata save failures."""
        # Make cache directory read-only (simulate save failure)
        with patch.object(self.cache, '_save_metadata', side_effect=OSError("Save failed")):
            # Should not raise exception
            self.cache.cache_repo("https://test.com/repo", "main", Path("/tmp/nonexistent"))

    def test_cache_cleanup_error_handling(self):
        """Test that cache cleanup handles errors gracefully."""
        # Add an entry with invalid path
        self.cache._metadata['invalid'] = {
            'repo_url': 'invalid',
            'branch': 'invalid',
            'cached_at': time.time()
        }

        # Should not raise exceptions during cleanup
        self.cache._cleanup_old_cache()

        # Should complete successfully
        assert True