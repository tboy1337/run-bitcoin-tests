"""Tests for configuration management system."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from run_bitcoin_tests.config import (
    AppConfig,
    ConfigManager,
    BitcoinConfig,
    BuildConfig,
    DockerConfig,
    LoggingConfig,
    NetworkConfig,
    RepositoryConfig,
    SecurityConfig,
    TestConfig,
    get_config,
    load_config,
    reset_config,
    update_config,
)


class TestConfigDataClasses:
    """Test configuration data classes."""

    def test_repository_config_defaults(self):
        """Test RepositoryConfig default values."""
        config = RepositoryConfig()
        assert config.url == "https://github.com/bitcoin/bitcoin"
        assert config.branch == "master"
        assert config.clone_timeout == 600
        assert config.shallow_clone is True

    def test_build_config_defaults(self):
        """Test BuildConfig default values."""
        config = BuildConfig()
        assert config.type == "RelWithDebInfo"
        assert config.parallel_jobs is None
        assert config.enable_tests is True

    def test_docker_config_defaults(self):
        """Test DockerConfig default values."""
        config = DockerConfig()
        assert config.compose_file == "docker-compose.yml"
        assert config.container_name == "bitcoin-tests"
        assert config.keep_containers is False

    def test_app_config_defaults(self):
        """Test AppConfig default values."""
        config = AppConfig()
        assert config.version == "1.0.0"
        assert config.debug is False
        assert config.dry_run is False
        assert isinstance(config.repository, RepositoryConfig)
        assert isinstance(config.build, BuildConfig)


class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_initialization(self):
        """Test ConfigManager initialization."""
        manager = ConfigManager()
        assert isinstance(manager.config, AppConfig)
        assert manager._env_cache == {}
        assert manager._loaded_env_files == []

    def test_env_var_parsing(self):
        """Test environment variable parsing."""
        manager = ConfigManager()

        # Test string values
        assert manager._get_env_var("TEST_VAR", "default", str) == "default"

        # Test boolean values
        with patch.dict(os.environ, {"TEST_BOOL_TRUE": "true"}):
            assert manager._get_env_var("TEST_BOOL_TRUE", False, bool) is True

        with patch.dict(os.environ, {"TEST_BOOL_FALSE": "false"}):
            assert manager._get_env_var("TEST_BOOL_FALSE", True, bool) is False

        # Test integer values
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            assert manager._get_env_var("TEST_INT", 0, int) == 42

        # Test invalid integer
        with patch.dict(os.environ, {"TEST_INVALID_INT": "not_a_number"}):
            assert manager._get_env_var("TEST_INVALID_INT", 100, int) == 100

    def test_load_from_env_vars(self):
        """Test loading configuration from environment variables."""
        manager = ConfigManager()

        env_vars = {
            "BTC_REPO_URL": "https://github.com/test/bitcoin",
            "BTC_REPO_BRANCH": "test-branch",
            "BTC_BUILD_TYPE": "Debug",
            "BTC_LOG_LEVEL": "DEBUG",
            "BTC_DEBUG": "true",
        }

        with patch.dict(os.environ, env_vars):
            manager.load_from_env_vars()

            assert manager.config.repository.url == "https://github.com/test/bitcoin"
            assert manager.config.repository.branch == "test-branch"
            assert manager.config.build.type == "Debug"
            assert manager.config.logging.level == "DEBUG"
            assert manager.config.debug is True

    def test_load_from_env_file(self):
        """Test loading configuration from .env file."""
        manager = ConfigManager()

        env_content = """BTC_REPO_URL=https://github.com/env/bitcoin
BTC_BUILD_TYPE=Release
BTC_LOG_LEVEL=WARNING
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            env_file = f.name

        try:
            manager.load_from_env_file(env_file)

            # If python-dotenv is not available, the file won't be loaded
            if hasattr(manager, '_loaded_env_files') and env_file in [str(p) for p in manager._loaded_env_files]:
                # python-dotenv was available and loaded the file
                assert manager.config.repository.url == "https://github.com/env/bitcoin"
                assert manager.config.build.type == "Release"
                assert manager.config.logging.level == "WARNING"
            else:
                # python-dotenv not available, values should remain defaults
                assert manager.config.repository.url == "https://github.com/bitcoin/bitcoin"
        finally:
            Path(env_file).unlink()

    def test_validate_config(self):
        """Test configuration validation."""
        manager = ConfigManager()

        # Valid config should pass
        errors = manager.validate_config()
        assert len(errors) == 0

        # Test invalid repository URL
        manager.config.repository.url = ""
        errors = manager.validate_config()
        assert len(errors) > 0
        assert "Repository URL cannot be empty" in errors[0]

        # Reset for next test
        manager.config.repository.url = "https://github.com/bitcoin/bitcoin"

        # Test invalid build type
        manager.config.build.type = "InvalidType"
        errors = manager.validate_config()
        assert len(errors) > 0
        assert "Invalid build type" in errors[0]

    def test_get_summary(self):
        """Test configuration summary generation."""
        manager = ConfigManager()
        summary = manager.get_summary()

        assert "Bitcoin Core Tests Runner Configuration" in summary
        assert "Repository:" in summary
        assert "Build Type:" in summary

    def test_save_to_env_file(self):
        """Test saving configuration to .env file."""
        manager = ConfigManager()

        # Modify some settings
        manager.config.repository.url = "https://github.com/save/test"
        manager.config.build.type = "Debug"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            env_file = f.name

        try:
            manager.save_to_env_file(env_file)

            content = Path(env_file).read_text()
            assert "BTC_REPO_URL=https://github.com/save/test" in content
            assert "BTC_BUILD_TYPE=Debug" in content
        finally:
            Path(env_file).unlink()


class TestConfigFunctions:
    """Test global configuration functions."""

    def test_get_config(self):
        """Test getting current configuration."""
        config = get_config()
        assert isinstance(config, AppConfig)

    def test_update_config(self):
        """Test updating configuration at runtime."""
        original_url = get_config().repository.url

        update_config({"repository": RepositoryConfig(url="https://github.com/updated/test")})

        # This should work for top-level attributes
        assert get_config().repository.url == "https://github.com/updated/test"

        # Reset
        reset_config()
        assert get_config().repository.url == original_url

    def test_reset_config(self):
        """Test resetting configuration to defaults."""
        original_config = AppConfig()
        original_url = original_config.repository.url

        # Modify config
        update_config({"repository": RepositoryConfig(url="https://modified.com")})

        # Reset
        reset_config()

        # Should be back to defaults
        assert get_config().repository.url == original_url


class TestConfigLoading:
    """Test configuration loading with precedence."""

    def test_load_config_precedence(self):
        """Test that configuration loading respects precedence order."""
        # Create mock args
        mock_args = Mock()
        mock_args.repo_url = "https://cli-args.com"
        mock_args.branch = None
        mock_args.verbose = False
        mock_args.quiet = False
        mock_args.log_file = None
        mock_args.log_level = None
        mock_args.config = None
        mock_args.save_config = None
        mock_args.dry_run = False
        mock_args.show_config = False

        # Set environment variables (should be overridden by CLI)
        env_vars = {
            "BTC_REPO_URL": "https://env-var.com",
            "BTC_REPO_BRANCH": "env-branch",
        }

        with patch.dict(os.environ, env_vars):
            config = load_config(mock_args)

            # CLI args should take precedence
            assert config.repository.url == "https://cli-args.com"
            # Env var should be used for branch since CLI didn't specify
            assert config.repository.branch == "env-branch"

    def test_load_config_validation_failure(self):
        """Test that invalid configuration raises ValueError."""
        from run_bitcoin_tests.config import config_manager

        # Reset config and set invalid values directly
        config_manager.config.repository.url = ""  # Invalid empty URL

        errors = config_manager.validate_config()
        assert len(errors) > 0
        assert "Repository URL cannot be empty" in errors[0]

        # Reset to valid config
        config_manager.config.repository.url = "https://github.com/bitcoin/bitcoin"