"""
Tests for cross_platform_utils.py module.

This module contains comprehensive tests for cross-platform utilities,
ensuring consistent behavior across Windows, macOS, and Linux.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.cross_platform_utils import (
    PlatformInfo,
    CrossPlatformCommand,
    PathUtils,
    get_platform_info,
    get_cross_platform_command,
    get_path_utils,
    is_cross_platform_compatible
)


class TestPlatformInfo:
    """Test cases for PlatformInfo class."""

    def test_initialization(self):
        """Test PlatformInfo initialization detects platform correctly."""
        info = PlatformInfo()

        # Check that platform detection works
        assert hasattr(info, 'system')
        assert hasattr(info, 'is_windows')
        assert hasattr(info, 'is_linux')
        assert hasattr(info, 'is_macos')
        assert hasattr(info, 'is_unix')

        # Check that exactly one platform flag is True
        platform_flags = [info.is_windows, info.is_linux, info.is_macos]
        assert sum(platform_flags) == 1  # Exactly one should be True

        # Check architecture detection
        assert hasattr(info, 'is_x86')
        assert hasattr(info, 'is_arm')

    def test_command_detection(self):
        """Test that command availability detection works."""
        info = PlatformInfo()

        # These should be boolean values
        assert isinstance(info.has_docker, bool)
        assert isinstance(info.has_docker_compose, bool)
        assert isinstance(info.has_git, bool)
        assert isinstance(info.has_ping, bool)

    def test_path_separator(self):
        """Test platform-specific path separator."""
        info = PlatformInfo()
        separator = info.get_path_separator()

        if info.is_windows:
            assert separator == ';'
        else:
            assert separator == ':'

    def test_executable_extension(self):
        """Test platform-specific executable extension."""
        info = PlatformInfo()
        ext = info.get_executable_extension()

        if info.is_windows:
            assert ext == '.exe'
        else:
            assert ext == ''

    def test_unicode_support(self):
        """Test Unicode support detection."""
        info = PlatformInfo()
        supports_unicode = info.supports_unicode()
        assert isinstance(supports_unicode, bool)

    def test_directory_methods(self):
        """Test directory-related methods."""
        info = PlatformInfo()

        temp_dir = info.get_temp_directory()
        assert isinstance(temp_dir, Path)
        assert temp_dir.exists() or temp_dir.parent.exists()

        home_dir = info.get_home_directory()
        assert isinstance(home_dir, Path)
        assert home_dir.exists()

        cache_dir = info.get_cache_directory()
        assert isinstance(cache_dir, Path)
        # Cache directory might not exist yet, but should be a valid path


class TestCrossPlatformCommand:
    """Test cases for CrossPlatformCommand class."""

    def test_ping_command_windows(self):
        """Test ping command generation for Windows."""
        with patch('run_bitcoin_tests.cross_platform_utils.PlatformInfo') as mock_platform:
            mock_platform.return_value.is_windows = True
            cmd = CrossPlatformCommand()
            ping_cmd = cmd.get_ping_command('example.com', 5)
            assert ping_cmd == ['ping', '-n', '1', '-w', '5000', 'example.com']

    def test_ping_command_unix(self):
        """Test ping command generation for Unix-like systems."""
        with patch('run_bitcoin_tests.cross_platform_utils.PlatformInfo') as mock_platform:
            mock_platform.return_value.is_windows = False
            cmd = CrossPlatformCommand()
            ping_cmd = cmd.get_ping_command('example.com', 3)
            assert ping_cmd == ['ping', '-c', '1', '-W', '3', 'example.com']

    @patch('run_bitcoin_tests.cross_platform_utils.CrossPlatformCommand._check_command_exists')
    def test_docker_compose_command_preference(self, mock_check):
        """Test docker compose command preference."""
        cmd = CrossPlatformCommand()

        # Test preference for 'docker compose'
        mock_check.side_effect = lambda c: 'docker compose version' in ' '.join(c)
        result = cmd.get_docker_compose_command()
        assert result == ['docker', 'compose']

        # Test fallback to 'docker-compose'
        mock_check.side_effect = lambda c: 'docker-compose version' in ' '.join(c)
        result = cmd.get_docker_compose_command()
        assert result == ['docker-compose']

    def test_docker_compose_command_not_found(self):
        """Test docker compose command when neither is available."""
        cmd = CrossPlatformCommand()

        with patch.object(cmd, '_check_command_exists', return_value=False):
            with pytest.raises(FileNotFoundError, match="Neither 'docker compose' nor 'docker-compose' found"):
                cmd.get_docker_compose_command()

    def test_normalize_command_args_windows(self):
        """Test command argument normalization on Windows."""
        with patch('run_bitcoin_tests.cross_platform_utils.PlatformInfo') as mock_platform:
            mock_platform.return_value.is_windows = True
            cmd = CrossPlatformCommand()

            args = ['git', 'clone', 'https://example.com/repo', '--branch', 'main']
            normalized = cmd.normalize_command_args(args)
            assert normalized == args  # Should not change non-path args

    def test_normalize_command_args_unix(self):
        """Test command argument normalization on Unix."""
        with patch('run_bitcoin_tests.cross_platform_utils.PlatformInfo') as mock_platform:
            mock_platform.return_value.is_windows = False
            cmd = CrossPlatformCommand()

            args = ['git', 'clone', 'https://example.com/repo']
            normalized = cmd.normalize_command_args(args)
            assert normalized == args  # Should not change on Unix


class TestPathUtils:
    """Test cases for PathUtils class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.path_utils = PathUtils()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_path(self):
        """Test path normalization."""
        # Test with regular path
        path = self.temp_dir / "test" / "file.txt"
        normalized = self.path_utils.normalize_path(path)
        assert isinstance(normalized, Path)

        # Test with user expansion (if supported)
        if os.name != 'nt':  # Skip on Windows where ~ expansion might not work
            home_path = Path("~")
            normalized_home = self.path_utils.normalize_path(home_path)
            assert isinstance(normalized_home, Path)

    def test_ensure_directory(self):
        """Test directory creation."""
        test_dir = self.temp_dir / "new_test_dir" / "subdir"
        result = self.path_utils.ensure_directory(test_dir)
        assert result.exists()
        assert result.is_dir()

    def test_is_safe_path(self):
        """Test safe path validation."""
        base_dir = self.temp_dir / "base"
        base_dir.mkdir()

        # Safe paths
        safe_path = base_dir / "file.txt"
        assert self.path_utils.is_safe_path(safe_path, base_dir)

        safe_subdir = base_dir / "subdir" / "file.txt"
        assert self.path_utils.is_safe_path(safe_subdir, base_dir)

        # Unsafe paths (path traversal)
        unsafe_path = base_dir / ".." / "outside.txt"
        assert not self.path_utils.is_safe_path(unsafe_path, base_dir)

        # Absolute paths outside base
        if os.name != 'nt':  # Unix-like systems
            outside_abs = Path("/tmp/outside.txt")
            assert not self.path_utils.is_safe_path(outside_abs, base_dir)

    def test_get_relative_path(self):
        """Test relative path calculation."""
        base_dir = self.temp_dir / "base"
        base_dir.mkdir()

        sub_path = base_dir / "sub" / "file.txt"
        relative = self.path_utils.get_relative_path(sub_path, base_dir)
        assert str(relative) == "sub/file.txt"

        # Test with non-relative paths
        outside_path = Path("/tmp/outside.txt")
        abs_result = self.path_utils.get_relative_path(outside_path, base_dir)
        assert abs_result.is_absolute()


class TestGlobalFunctions:
    """Test global functions in cross_platform_utils."""

    def test_get_platform_info_singleton(self):
        """Test that get_platform_info returns singleton."""
        info1 = get_platform_info()
        info2 = get_platform_info()

        assert info1 is info2
        assert isinstance(info1, PlatformInfo)

    def test_get_cross_platform_command_singleton(self):
        """Test that get_cross_platform_command returns singleton."""
        cmd1 = get_cross_platform_command()
        cmd2 = get_cross_platform_command()

        assert cmd1 is cmd2
        assert isinstance(cmd1, CrossPlatformCommand)

    def test_get_path_utils_singleton(self):
        """Test that get_path_utils returns singleton."""
        utils1 = get_path_utils()
        utils2 = get_path_utils()

        assert utils1 is utils2
        assert isinstance(utils1, PathUtils)

    def test_is_cross_platform_compatible(self):
        """Test cross-platform compatibility check."""
        results = is_cross_platform_compatible()

        required_keys = [
            'has_docker', 'has_docker_compose', 'has_git', 'has_ping',
            'supports_unicode', 'python_version_compatible', 'docker_compose_command_available'
        ]

        for key in required_keys:
            assert key in results
            assert isinstance(results[key], bool)


class TestIntegration:
    """Integration tests for cross-platform utilities."""

    def test_platform_info_consistency(self):
        """Test that platform info is consistent across calls."""
        info1 = get_platform_info()
        info2 = get_platform_info()

        assert info1.system == info2.system
        assert info1.is_windows == info2.is_windows
        assert info1.is_linux == info2.is_linux
        assert info1.is_macos == info2.is_macos

    def test_cross_platform_workflow(self):
        """Test a complete cross-platform workflow."""
        # Get platform info
        info = get_platform_info()
        assert hasattr(info, 'system')

        # Get command utilities
        cmd = get_cross_platform_command()
        ping_cmd = cmd.get_ping_command('localhost')
        assert isinstance(ping_cmd, list)
        assert len(ping_cmd) > 0

        # Get path utilities
        path_utils = get_path_utils()
        test_path = Path("test")
        normalized = path_utils.normalize_path(test_path)
        assert isinstance(normalized, Path)

    def test_environment_compatibility(self):
        """Test that the utilities work in the current environment."""
        compatibility = is_cross_platform_compatible()

        # At minimum, we should be able to check compatibility
        assert isinstance(compatibility, dict)
        assert len(compatibility) > 0

        # Python version should be compatible (assuming we're running on a supported version)
        assert compatibility.get('python_version_compatible', False)