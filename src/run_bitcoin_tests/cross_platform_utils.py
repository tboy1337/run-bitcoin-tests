"""
Cross-platform utilities for the Bitcoin Core tests runner.

This module provides utilities to ensure consistent behavior across
Windows, macOS, and Linux platforms, handling platform-specific differences
in file systems, commands, and system interactions.

Key Features:
- Platform detection and feature availability
- Cross-platform command execution
- Path handling and normalization
- File permission handling
- Environment variable management
- System information gathering

Classes:
    PlatformInfo: Information about the current platform and capabilities
    CrossPlatformCommand: Cross-platform command execution utilities
    PathUtils: Cross-platform path manipulation utilities
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union


class PlatformInfo:  # pylint: disable=too-many-instance-attributes
    """
    Information about the current platform and its capabilities.

    Provides a centralized way to detect platform features and capabilities,
    ensuring consistent behavior across different operating systems.
    """

    def __init__(self):
        """Initialize platform information."""
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.version = platform.version()
        self.python_version = sys.version_info

        # Platform-specific flags
        self.is_windows = self.system == "windows"
        self.is_linux = self.system == "linux"
        self.is_macos = self.system == "darwin"
        self.is_unix = not self.is_windows

        # Architecture flags
        self.is_x86 = "x86" in self.machine or "amd64" in self.machine
        self.is_arm = "arm" in self.machine or "aarch64" in self.machine

        # Feature detection
        self.has_docker = self._check_command("docker")
        self.has_docker_compose = self._check_command("docker-compose") or self._check_command(
            "docker compose"
        )
        self.has_git = self._check_command("git")
        self.has_ping = self._check_command("ping")

    def _check_command(self, command: str) -> bool:
        """Check if a command is available on the system."""
        try:
            subprocess.run([command, "--version"], capture_output=True, timeout=5, check=False)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def get_path_separator(self) -> str:
        """Get the platform-specific path separator."""
        return ";" if self.is_windows else ":"

    def get_executable_extension(self) -> str:
        """Get the platform-specific executable extension."""
        return ".exe" if self.is_windows else ""

    def supports_unicode(self) -> bool:
        """Check if the platform supports Unicode output."""
        # Most modern systems support Unicode, but Windows console might not
        if self.is_windows:
            # Check if we're running in a Unicode-capable terminal
            try:
                import ctypes  # pylint: disable=import-outside-toplevel

                kernel32 = ctypes.windll.kernel32
                return bool(kernel32.GetConsoleOutputCP())
            except (AttributeError, OSError):
                return False
        return True

    def get_temp_directory(self) -> Path:
        """Get the platform-specific temporary directory."""
        # Use pathlib for cross-platform temp directory
        if self.is_windows:
            return Path(os.environ.get("TEMP", "C:\\Temp"))
        return Path("/tmp")

    def get_home_directory(self) -> Path:
        """Get the user's home directory in a cross-platform way."""
        return Path.home()

    def get_cache_directory(self) -> Path:
        """Get the platform-specific cache directory."""
        if self.is_windows:
            # Windows: %LOCALAPPDATA%\bitcoin-tests
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                return Path(local_appdata) / "bitcoin-tests"
            return self.get_home_directory() / "AppData" / "Local" / "bitcoin-tests"
        if self.is_macos:
            # macOS: ~/Library/Caches/bitcoin-tests
            return self.get_home_directory() / "Library" / "Caches" / "bitcoin-tests"
        # Linux/Unix: ~/.cache/bitcoin-tests or XDG_CACHE_HOME
        cache_home = os.environ.get("XDG_CACHE_HOME")
        if cache_home:
            return Path(cache_home) / "bitcoin-tests"
        return self.get_home_directory() / ".cache" / "bitcoin-tests"


class CrossPlatformCommand:
    """
    Cross-platform command execution utilities.

    Handles platform-specific differences in command syntax and behavior,
    ensuring consistent command execution across platforms.
    """

    def __init__(self):
        """Initialize cross-platform command utilities."""
        self.platform = PlatformInfo()

    def get_ping_command(self, host: str, timeout: int = 5) -> List[str]:
        """
        Get the platform-specific ping command.

        Args:
            host: Host to ping
            timeout: Timeout in seconds

        Returns:
            Ping command as a list of arguments
        """
        if self.platform.is_windows:
            return ["ping", "-n", "1", "-w", str(timeout * 1000), host]
        return ["ping", "-c", "1", "-W", str(timeout), host]

    def get_docker_compose_command(self) -> List[str]:
        """
        Get the appropriate docker-compose command for the platform.

        Returns:
            Docker compose command as a list
        """
        # Try 'docker compose' first (newer versions)
        if self._check_command_exists(["docker", "compose", "version"]):
            return ["docker", "compose"]
        # Fall back to 'docker-compose'
        if self._check_command_exists(["docker-compose", "version"]):
            return ["docker-compose"]
        raise FileNotFoundError("Neither 'docker compose' nor 'docker-compose' found")

    @staticmethod
    def _check_command_exists(command: List[str]) -> bool:
        """Check if a command exists and is executable."""
        try:
            result = subprocess.run(command, capture_output=True, timeout=10, check=False)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def normalize_command_args(self, args: List[str]) -> List[str]:
        """
        Normalize command arguments for cross-platform execution.

        Args:
            args: Command arguments

        Returns:
            Normalized command arguments
        """
        # On Windows, ensure commands use backslashes in paths
        if self.platform.is_windows:
            normalized = []
            for arg in args:
                # Convert forward slashes to backslashes in paths (but not URLs)
                if "/" in arg and "\\" not in arg and not arg.startswith("-"):
                    # Don't convert URLs
                    if arg.startswith(("http://", "https://")):
                        normalized.append(arg)
                    # Simple heuristic: if it looks like a path, convert
                    elif "." in arg or "/" in arg:
                        normalized.append(arg.replace("/", "\\"))
                    else:
                        normalized.append(arg)
                else:
                    normalized.append(arg)
            return normalized
        return args


class PathUtils:
    """
    Cross-platform path manipulation utilities.

    Provides consistent path handling across different platforms,
    handling differences in path separators, case sensitivity, etc.
    """

    def __init__(self):
        """Initialize path utilities."""
        self.platform = PlatformInfo()

    def normalize_path(self, path: Union[str, Path]) -> Path:
        """
        Normalize a path for cross-platform compatibility.

        Args:
            path: Path to normalize

        Returns:
            Normalized Path object
        """
        path_obj = Path(path)

        # Expand user directory
        if str(path).startswith("~"):
            path_obj = path_obj.expanduser()

        # Resolve any relative components
        try:
            path_obj = path_obj.resolve()
        except (OSError, RuntimeError):
            # Path might not exist yet, that's okay
            pass

        return path_obj

    def ensure_directory(self, path: Union[str, Path]) -> Path:
        """
        Ensure a directory exists, creating it if necessary.

        Args:
            path: Directory path

        Returns:
            Path to the ensured directory
        """
        path_obj = self.normalize_path(path)
        path_obj.mkdir(parents=True, exist_ok=True)
        return path_obj

    def is_safe_path(
        self, path: Union[str, Path], base_dir: Optional[Union[str, Path]] = None
    ) -> bool:
        """
        Check if a path is safe (doesn't escape the base directory).

        Args:
            path: Path to check
            base_dir: Base directory (default: current working directory)

        Returns:
            True if path is safe, False otherwise
        """
        try:
            path_obj = self.normalize_path(path)
            base_path = self.normalize_path(base_dir or Path.cwd())

            # Check for path traversal
            try:
                path_obj.relative_to(base_path)
                return True
            except ValueError:
                return False

        except (OSError, RuntimeError):
            return False

    def get_relative_path(self, path: Union[str, Path], base: Union[str, Path]) -> Path:
        """
        Get a path relative to a base directory.

        Args:
            path: Path to make relative
            base: Base directory

        Returns:
            Relative path
        """
        try:
            return self.normalize_path(path).relative_to(self.normalize_path(base))
        except ValueError:
            # Paths are not relative, return absolute path
            return self.normalize_path(path)


# Global instances (module-level singletons)
_platform_info = None  # pylint: disable=invalid-name
_cross_platform_command = None  # pylint: disable=invalid-name
_path_utils = None  # pylint: disable=invalid-name


def get_platform_info() -> PlatformInfo:
    """Get the global platform info instance."""
    global _platform_info  # pylint: disable=global-statement
    if _platform_info is None:
        _platform_info = PlatformInfo()
    return _platform_info


def get_cross_platform_command() -> CrossPlatformCommand:
    """Get the global cross-platform command instance."""
    global _cross_platform_command  # pylint: disable=global-statement
    if _cross_platform_command is None:
        _cross_platform_command = CrossPlatformCommand()
    return _cross_platform_command


def get_path_utils() -> PathUtils:
    """Get the global path utils instance."""
    global _path_utils  # pylint: disable=global-statement
    if _path_utils is None:
        _path_utils = PathUtils()
    return _path_utils


def is_cross_platform_compatible() -> Dict[str, bool]:
    """
    Check if the current environment is cross-platform compatible.

    Returns:
        Dictionary of compatibility checks
    """
    info = get_platform_info()
    cmd = get_cross_platform_command()

    results = {
        "has_docker": info.has_docker,
        "has_docker_compose": info.has_docker_compose,
        "has_git": info.has_git,
        "has_ping": info.has_ping,
        "supports_unicode": info.supports_unicode(),
        "python_version_compatible": info.python_version >= (3, 8),
    }

    # Try to get docker compose command
    try:
        cmd.get_docker_compose_command()
        results["docker_compose_command_available"] = True
    except FileNotFoundError:
        results["docker_compose_command_available"] = False

    return results
