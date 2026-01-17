"""
Configuration management for the Bitcoin Core tests runner.

This module provides a comprehensive configuration system supporting:
- Environment variables with automatic type conversion
- .env files (optional, requires python-dotenv)
- Default values with type validation
- Configuration precedence (CLI > env > .env > defaults)
- Runtime configuration updates

Configuration Sources (in order of precedence):
1. Command line arguments (highest precedence)
2. Environment variables (BTC_* prefixed)
3. .env files (.env, .env.local, .env.production, etc.)
4. Default values (lowest precedence)

Environment Variables:
- BTC_REPO_URL: Repository URL to clone
- BTC_REPO_BRANCH: Branch to clone
- BTC_BUILD_TYPE: CMake build type (Debug, Release, RelWithDebInfo, MinSizeRel)
- BTC_BUILD_JOBS: Number of parallel build jobs
- BTC_LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- BTC_TEST_TIMEOUT: Test execution timeout in seconds
- And many more...

Example Usage:
    from run_bitcoin_tests.config import load_config, get_config

    # Load configuration from all sources
    config = load_config(cli_args)

    # Access configuration values
    repo_url = config.repository.url
    build_type = config.build.type
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .logging_config import get_logger

logger = get_logger(__name__)

from .logging_config import get_logger

logger = get_logger(__name__)

# Try to import python-dotenv for .env file support
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    logger.warning("python-dotenv not available, .env file support disabled")


@dataclass
class RepositoryConfig:
    """Repository-related configuration."""
    url: str = "https://github.com/bitcoin/bitcoin"
    branch: str = "master"
    clone_timeout: int = 600  # seconds
    clone_retries: int = 3
    clone_retry_delay: int = 10
    shallow_clone: bool = True
    clone_depth: int = 1


@dataclass
class BuildConfig:
    """Build-related configuration."""
    type: str = "RelWithDebInfo"  # Debug, Release, RelWithDebInfo, MinSizeRel
    parallel_jobs: Optional[int] = None  # None = auto-detect
    cmake_args: List[str] = field(default_factory=list)
    make_args: List[str] = field(default_factory=list)
    enable_tests: bool = True
    enable_fuzz_tests: bool = False


@dataclass
class DockerConfig:
    """Docker-related configuration."""
    compose_file: str = "docker-compose.yml"
    build_context: str = "."
    build_timeout: int = 1800  # seconds
    container_name: str = "bitcoin-tests"
    image_name: str = "bitcoin-tests"
    keep_containers: bool = False
    docker_host: Optional[str] = None


@dataclass
class NetworkConfig:
    """Network-related configuration."""
    timeout: int = 300  # seconds
    retries: int = 3
    retry_delay: int = 5
    user_agent: str = "bitcoin-tests-runner/1.0"
    proxy: Optional[str] = None
    no_proxy: List[str] = field(default_factory=list)
    use_git_cache: bool = True  # Enable Git repository caching
    cache_dir: Optional[str] = None  # Custom cache directory (None = default ~/.bitcoin_test_cache)
    max_cache_size_gb: float = 10.0  # Maximum cache size in GB


@dataclass
class ExecutionConfig:
    """Test execution configuration."""
    timeout: int = 3600  # seconds
    parallel: bool = True
    parallel_jobs: Optional[int] = None
    rerun_failures: int = 0
    capture_output: bool = True
    test_filter: Optional[str] = None
    test_data_dir: Optional[str] = None
    # Test suite selection
    test_suite: str = "both"  # "cpp", "python", or "both"
    python_test_scope: str = "standard"  # "all", "standard", "quick", or specific test pattern
    python_test_jobs: int = 4  # parallel jobs for Python tests
    cpp_test_args: str = ""  # arguments for C++ test_bitcoin executable
    python_test_args: str = ""  # arguments for test_runner.py
    exclude_python_tests: List[str] = field(default_factory=list)  # tests to exclude


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: Optional[str] = None
    format: str = "%(asctime)s - %(levelname)s - %(message)s"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    console_output: bool = True


@dataclass
class SecurityConfig:
    """Security-related configuration."""
    allow_insecure_ssl: bool = False
    trusted_hosts: List[str] = field(default_factory=lambda: ["github.com", "gitlab.com"])
    block_private_ips: bool = True
    max_url_length: int = 2048
    allowed_schemes: List[str] = field(default_factory=lambda: ["http", "https", "git", "ssh"])


@dataclass
class BitcoinConfig:
    """Bitcoin Core specific configuration."""
    version: Optional[str] = None
    commit_hash: Optional[str] = None
    test_bitcoin_path: str = "src/test/test_bitcoin"
    functional_test_dir: str = "test/functional"
    fuzz_test_dir: str = "test/fuzz"


@dataclass
class AppConfig:
    """Main application configuration."""
    repository: RepositoryConfig = field(default_factory=RepositoryConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    test: ExecutionConfig = field(default_factory=ExecutionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    bitcoin: BitcoinConfig = field(default_factory=BitcoinConfig)

    # Application metadata
    version: str = "1.0.0"
    debug: bool = False
    dry_run: bool = False
    verbose: bool = False
    quiet: bool = False


class ConfigManager:
    """Configuration manager with support for multiple sources."""

    def __init__(self):
        self.config = AppConfig()
        self._env_cache: Dict[str, Any] = {}
        self._loaded_env_files: List[Path] = []

    def load_from_env_file(self, env_file: Union[str, Path]) -> None:
        """Load configuration from .env file."""
        env_path = Path(env_file)

        if not env_path.exists():
            logger.debug(f"Environment file {env_path} does not exist, skipping")
            return

        if not HAS_DOTENV:
            logger.warning(f"Cannot load {env_path}: python-dotenv not installed")
            return

        logger.info(f"Loading configuration from {env_path}")
        load_dotenv(env_path)
        self._loaded_env_files.append(env_path)

    def load_from_env_vars(self) -> None:
        """Load configuration from environment variables."""
        logger.debug("Loading configuration from environment variables")

        # Repository settings
        self.config.repository.url = self._get_env_var("BTC_REPO_URL", self.config.repository.url)
        self.config.repository.branch = self._get_env_var("BTC_REPO_BRANCH", self.config.repository.branch)
        self.config.repository.clone_timeout = self._get_env_var("BTC_CLONE_TIMEOUT", self.config.repository.clone_timeout, int)
        self.config.repository.clone_retries = self._get_env_var("BTC_CLONE_RETRIES", self.config.repository.clone_retries, int)
        self.config.repository.shallow_clone = self._get_env_var("BTC_SHALLOW_CLONE", self.config.repository.shallow_clone, bool)

        # Build settings
        self.config.build.type = self._get_env_var("BTC_BUILD_TYPE", self.config.build.type)
        self.config.build.parallel_jobs = self._get_env_var("BTC_BUILD_JOBS", self.config.build.parallel_jobs, int)
        self.config.build.enable_tests = self._get_env_var("BTC_ENABLE_TESTS", self.config.build.enable_tests, bool)

        # Docker settings
        self.config.docker.compose_file = self._get_env_var("BTC_COMPOSE_FILE", self.config.docker.compose_file)
        self.config.docker.container_name = self._get_env_var("BTC_CONTAINER_NAME", self.config.docker.container_name)
        self.config.docker.keep_containers = self._get_env_var("BTC_KEEP_CONTAINERS", self.config.docker.keep_containers, bool)
        self.config.docker.docker_host = self._get_env_var("DOCKER_HOST", self.config.docker.docker_host)

        # Network settings
        self.config.network.timeout = self._get_env_var("BTC_NETWORK_TIMEOUT", self.config.network.timeout, int)
        self.config.network.retries = self._get_env_var("BTC_NETWORK_RETRIES", self.config.network.retries, int)
        self.config.network.proxy = self._get_env_var("HTTPS_PROXY", self.config.network.proxy) or self._get_env_var("HTTP_PROXY", self.config.network.proxy)

        # Test settings
        self.config.test.timeout = self._get_env_var("BTC_TEST_TIMEOUT", self.config.test.timeout, int)
        self.config.test.parallel = self._get_env_var("BTC_TEST_PARALLEL", self.config.test.parallel, bool)
        self.config.test.parallel_jobs = self._get_env_var("BTC_TEST_JOBS", self.config.test.parallel_jobs, int)
        self.config.test.test_suite = self._get_env_var("BTC_TEST_SUITE", self.config.test.test_suite)
        self.config.test.python_test_scope = self._get_env_var("BTC_PYTHON_TEST_SCOPE", self.config.test.python_test_scope)
        self.config.test.python_test_jobs = self._get_env_var("BTC_PYTHON_TEST_JOBS", self.config.test.python_test_jobs, int)
        self.config.test.cpp_test_args = self._get_env_var("BTC_CPP_TEST_ARGS", self.config.test.cpp_test_args)
        self.config.test.python_test_args = self._get_env_var("BTC_PYTHON_TEST_ARGS", self.config.test.python_test_args)

        # Logging settings
        self.config.logging.level = self._get_env_var("BTC_LOG_LEVEL", self.config.logging.level)
        self.config.logging.file = self._get_env_var("BTC_LOG_FILE", self.config.logging.file)

        # Security settings
        self.config.security.allow_insecure_ssl = self._get_env_var("BTC_ALLOW_INSECURE_SSL", self.config.security.allow_insecure_ssl, bool)

        # Application settings
        self.config.debug = self._get_env_var("BTC_DEBUG", self.config.debug, bool)
        self.config.dry_run = self._get_env_var("BTC_DRY_RUN", self.config.dry_run, bool)
        self.config.verbose = self._get_env_var("BTC_VERBOSE", self.config.verbose, bool)
        self.config.quiet = self._get_env_var("BTC_QUIET", self.config.quiet, bool)

    def update_from_cli_args(self, args: Any) -> None:
        """Update configuration from command line arguments."""
        logger.debug("Updating configuration from CLI arguments")

        # Repository settings
        if hasattr(args, 'repo_url') and args.repo_url:
            self.config.repository.url = args.repo_url
        if hasattr(args, 'branch') and args.branch:
            self.config.repository.branch = args.branch

        # Logging settings
        if hasattr(args, 'verbose') and args.verbose:
            self.config.verbose = True
            self.config.logging.level = "DEBUG"
        if hasattr(args, 'quiet') and args.quiet:
            self.config.quiet = True
            self.config.logging.level = "ERROR"
        if hasattr(args, 'log_file') and args.log_file:
            self.config.logging.file = args.log_file
        if hasattr(args, 'log_level') and args.log_level:
            self.config.logging.level = args.log_level

        # Performance settings
        if hasattr(args, 'no_cache') and args.no_cache:
            self.config.network.use_git_cache = False
        if hasattr(args, 'performance_monitor') and args.performance_monitor:
            # This could be used to enable more detailed monitoring
            # For now, we just set a flag that can be checked
            pass

        # Test suite settings
        if hasattr(args, 'test_suite') and args.test_suite:
            self.config.test.test_suite = args.test_suite
        if hasattr(args, 'cpp_only') and args.cpp_only:
            self.config.test.test_suite = "cpp"
        if hasattr(args, 'python_only') and args.python_only:
            self.config.test.test_suite = "python"
        if hasattr(args, 'python_tests') and args.python_tests:
            self.config.test.python_test_scope = args.python_tests
        if hasattr(args, 'python_jobs') and args.python_jobs:
            self.config.test.python_test_jobs = args.python_jobs
        if hasattr(args, 'exclude_test') and args.exclude_test:
            self.config.test.exclude_python_tests = args.exclude_test
        if hasattr(args, 'build_jobs') and args.build_jobs:
            self.config.build.parallel_jobs = args.build_jobs
        if hasattr(args, 'build_type') and args.build_type:
            self.config.build.type = args.build_type
        if hasattr(args, 'keep_containers') and args.keep_containers:
            self.config.docker.keep_containers = args.keep_containers

    def _get_env_var(self, name: str, default: Any, var_type: type = str) -> Any:
        """Get environment variable with type conversion."""
        value = os.environ.get(name)
        if value is None:
            return default

        # Cache the parsed value
        cache_key = f"{name}:{value}:{var_type.__name__}"
        if cache_key in self._env_cache:
            return self._env_cache[cache_key]

        try:
            if var_type == bool:
                # Handle boolean conversion
                lower_value = value.lower()
                if lower_value in ('true', '1', 'yes', 'on'):
                    parsed = True
                elif lower_value in ('false', '0', 'no', 'off'):
                    parsed = False
                else:
                    parsed = default
            elif var_type == int:
                parsed = int(value)
            elif var_type == float:
                parsed = float(value)
            elif var_type == list:
                # Handle comma-separated lists
                parsed = [item.strip() for item in value.split(',') if item.strip()]
            else:
                parsed = value

            self._env_cache[cache_key] = parsed
            return parsed

        except (ValueError, TypeError):
            logger.warning(f"Invalid value for {name}={value}, using default {default}")
            return default

    def validate_config(self) -> List[str]:
        """Validate the current configuration and return any errors."""
        errors = []

        # Validate repository URL
        if not self.config.repository.url:
            errors.append("Repository URL cannot be empty")

        # Validate URLs are reasonable length
        if len(self.config.repository.url) > self.config.security.max_url_length:
            errors.append(f"Repository URL too long (max {self.config.security.max_url_length} characters)")

        # Validate build type
        valid_build_types = ["Debug", "Release", "RelWithDebInfo", "MinSizeRel"]
        if self.config.build.type not in valid_build_types:
            errors.append(f"Invalid build type '{self.config.build.type}'. Valid options: {valid_build_types}")

        # Validate timeouts are reasonable
        if self.config.repository.clone_timeout < 30:
            errors.append("Clone timeout must be at least 30 seconds")
        if self.config.test.timeout < 60:
            errors.append("Test timeout must be at least 60 seconds")

        # Validate logging level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.config.logging.level.upper() not in valid_log_levels:
            errors.append(f"Invalid log level '{self.config.logging.level}'. Valid options: {valid_log_levels}")

        # Validate parallel jobs
        if self.config.build.parallel_jobs is not None and self.config.build.parallel_jobs < 1:
            errors.append("Parallel build jobs must be >= 1")
        if self.config.test.parallel_jobs is not None and self.config.test.parallel_jobs < 1:
            errors.append("Parallel test jobs must be >= 1")

        # Validate test suite selection
        valid_test_suites = ["cpp", "python", "both"]
        if self.config.test.test_suite not in valid_test_suites:
            errors.append(f"Invalid test suite '{self.config.test.test_suite}'. Valid options: {valid_test_suites}")

        # Validate Python test jobs
        if self.config.test.python_test_jobs < 1:
            errors.append("Python test jobs must be >= 1")

        return errors

    def get_summary(self) -> str:
        """Get a human-readable summary of the current configuration."""
        lines = [
            "Bitcoin Core Tests Runner Configuration",
            "=" * 40,
            f"Repository: {self.config.repository.url} (branch: {self.config.repository.branch})",
            f"Build Type: {self.config.build.type}",
            f"Parallel Jobs: {self.config.build.parallel_jobs or 'auto'}",
            f"Test Suite: {self.config.test.test_suite}",
            f"Test Timeout: {self.config.test.timeout}s",
            f"Log Level: {self.config.logging.level}",
            f"Debug Mode: {self.config.debug}",
            f"Dry Run: {self.config.dry_run}",
        ]

        # Add Python test details if Python tests are selected
        if self.config.test.test_suite in ["python", "both"]:
            lines.append(f"Python Test Scope: {self.config.test.python_test_scope}")
            lines.append(f"Python Test Jobs: {self.config.test.python_test_jobs}")

        if self.config.logging.file:
            lines.append(f"Log File: {self.config.logging.file}")

        if self.config.network.proxy:
            lines.append(f"Proxy: {self.config.network.proxy}")

        return "\n".join(lines)

    def save_to_env_file(self, env_file: Union[str, Path], include_comments: bool = True) -> None:
        """Save current configuration to .env file."""
        env_path = Path(env_file)

        lines = []
        if include_comments:
            lines.extend([
                "# Bitcoin Core Tests Runner Configuration",
                "# Generated automatically - edit as needed",
                "",
            ])

        # Repository settings
        lines.extend([
            f"BTC_REPO_URL={self.config.repository.url}",
            f"BTC_REPO_BRANCH={self.config.repository.branch}",
            f"BTC_CLONE_TIMEOUT={self.config.repository.clone_timeout}",
            f"BTC_CLONE_RETRIES={self.config.repository.clone_retries}",
            f"BTC_SHALLOW_CLONE={self.config.repository.shallow_clone}",
            "",
        ])

        # Build settings
        lines.extend([
            f"BTC_BUILD_TYPE={self.config.build.type}",
            f"BTC_BUILD_JOBS={self.config.build.parallel_jobs or ''}",
            f"BTC_ENABLE_TESTS={self.config.build.enable_tests}",
            "",
        ])

        # Docker settings
        lines.extend([
            f"BTC_COMPOSE_FILE={self.config.docker.compose_file}",
            f"BTC_CONTAINER_NAME={self.config.docker.container_name}",
            f"BTC_KEEP_CONTAINERS={self.config.docker.keep_containers}",
            "",
        ])

        # Network settings
        lines.extend([
            f"BTC_NETWORK_TIMEOUT={self.config.network.timeout}",
            f"BTC_NETWORK_RETRIES={self.config.network.retries}",
            "",
        ])

        # Test settings
        lines.extend([
            f"BTC_TEST_TIMEOUT={self.config.test.timeout}",
            f"BTC_TEST_PARALLEL={self.config.test.parallel}",
            f"BTC_TEST_JOBS={self.config.test.parallel_jobs or ''}",
            "",
        ])

        # Logging settings
        lines.extend([
            f"BTC_LOG_LEVEL={self.config.logging.level}",
            f"BTC_LOG_FILE={self.config.logging.file or ''}",
            "",
        ])

        # Application settings
        lines.extend([
            f"BTC_DEBUG={self.config.debug}",
            f"BTC_DRY_RUN={self.config.dry_run}",
            f"BTC_VERBOSE={self.config.verbose}",
            f"BTC_QUIET={self.config.quiet}",
        ])

        env_path.write_text("\n".join(lines), encoding='utf-8')
        logger.info(f"Configuration saved to {env_path}")


# Global configuration instance
config_manager = ConfigManager()


def load_config(args: Optional[Any] = None) -> AppConfig:
    """
    Load configuration from all sources with proper precedence.

    This function loads configuration in the following order:
    1. .env files (if available)
    2. Environment variables
    3. Command line arguments (if provided)
    4. Validates the final configuration

    Args:
        args: Optional command line arguments from argparse

    Returns:
        AppConfig: Fully loaded and validated configuration

    Raises:
        ValueError: If configuration validation fails
    """
    """
    Load configuration from all sources with proper precedence.

    Precedence order (highest to lowest):
    1. Command line arguments
    2. Environment variables
    3. .env files
    4. Default values
    """
    # Load from .env files first (lowest precedence except defaults)
    config_files = [".env", ".env.local", ".env.production", ".env.development"]
    for config_file in config_files:
        config_manager.load_from_env_file(config_file)

    # Load from environment variables
    config_manager.load_from_env_vars()

    # Update from CLI arguments (highest precedence)
    if args:
        config_manager.update_from_cli_args(args)

    # Validate configuration
    validation_errors = config_manager.validate_config()
    if validation_errors:
        logger.error("Configuration validation failed:")
        for error in validation_errors:
            logger.error(f"  - {error}")
        raise ValueError("Invalid configuration")

    logger.debug("Configuration loaded successfully")
    return config_manager.config


def get_config() -> AppConfig:
    """
    Get the current application configuration.

    Returns:
        AppConfig: The current configuration instance
    """
    return config_manager.config


def update_config(updates: Dict[str, Any]) -> None:
    """
    Update configuration values at runtime.

    This function allows dynamic configuration updates after the initial load.
    Only top-level configuration attributes can be updated this way.

    Args:
        updates: Dictionary of configuration key-value pairs to update

    Example:
        update_config({"repository": RepositoryConfig(url="https://new-repo.com")})
    """
    for key, value in updates.items():
        if hasattr(config_manager.config, key):
            setattr(config_manager.config, key, value)
            logger.debug(f"Updated configuration: {key}")
        else:
            logger.warning(f"Unknown configuration key: {key}")


def reset_config() -> None:
    """
    Reset configuration to default values.

    This function clears all loaded configuration and resets to the
    built-in default values. Useful for testing or when a clean
    configuration state is needed.
    """
    config_manager.config = AppConfig()
    config_manager._env_cache.clear()
    config_manager._loaded_env_files.clear()
    logger.info("Configuration reset to defaults")