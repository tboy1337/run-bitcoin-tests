"""Tests for input validation utilities."""

import pytest

from run_bitcoin_tests.validation import (
    validate_branch_name,
    validate_file_path,
    validate_git_url,
    sanitize_command_args,
    ValidationError,
)


class TestValidateGitUrl:
    """Test validate_git_url function."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        url = "https://github.com/bitcoin/bitcoin.git"
        result = validate_git_url(url)
        assert result == url

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        url = "http://github.com/bitcoin/bitcoin"
        result = validate_git_url(url)
        assert result == url

    def test_valid_git_url(self):
        """Test valid Git SSH URL."""
        url = "git@github.com:bitcoin/bitcoin.git"
        result = validate_git_url(url)
        assert result == url

    def test_empty_url(self):
        """Test empty URL."""
        with pytest.raises(ValidationError, match="Repository URL cannot be empty"):
            validate_git_url("")

    def test_whitespace_only_url(self):
        """Test whitespace-only URL."""
        with pytest.raises(ValidationError, match="Repository URL cannot be empty"):
            validate_git_url("   ")

    def test_invalid_scheme(self):
        """Test URL with invalid scheme."""
        with pytest.raises(ValidationError, match="Repository URL must start with"):
            validate_git_url("ftp://example.com/repo.git")

    def test_url_with_dangerous_characters(self):
        """Test URL containing dangerous characters."""
        with pytest.raises(ValidationError, match="contains invalid characters"):
            validate_git_url("https://github.com/bitcoin/bitcoin.git;rm -rf /")

    def test_malformed_url(self):
        """Test malformed URL."""
        with pytest.raises(ValidationError, match="Invalid repository URL format"):
            validate_git_url("https://")

    def test_url_without_domain(self):
        """Test URL without domain."""
        with pytest.raises(ValidationError, match="must include a valid domain"):
            validate_git_url("https:///path")


class TestValidateBranchName:
    """Test validate_branch_name function."""

    def test_valid_branch_name(self):
        """Test valid branch name."""
        branch = "feature/new-feature"
        result = validate_branch_name(branch)
        assert result == branch

    def test_valid_simple_branch(self):
        """Test simple valid branch name."""
        branch = "master"
        result = validate_branch_name(branch)
        assert result == branch

    def test_valid_branch_with_numbers(self):
        """Test branch name with numbers."""
        branch = "v2.1.0"
        result = validate_branch_name(branch)
        assert result == branch

    def test_empty_branch(self):
        """Test empty branch name."""
        with pytest.raises(ValidationError, match="Branch name cannot be empty"):
            validate_branch_name("")

    def test_whitespace_branch(self):
        """Test whitespace-only branch name."""
        with pytest.raises(ValidationError, match="Branch name cannot be empty"):
            validate_branch_name("   ")

    def test_branch_with_dangerous_chars(self):
        """Test branch name with dangerous characters."""
        with pytest.raises(ValidationError, match="contains invalid characters"):
            validate_branch_name("feature;rm -rf /")

    def test_branch_with_path_traversal(self):
        """Test branch name with path traversal."""
        with pytest.raises(ValidationError, match="contains invalid path components"):
            validate_branch_name("../etc/passwd")

    def test_branch_starting_with_dash(self):
        """Test branch name starting with dash."""
        with pytest.raises(ValidationError, match="cannot start with a dash"):
            validate_branch_name("-evil-branch")

    def test_branch_with_invalid_chars(self):
        """Test branch name with invalid characters."""
        with pytest.raises(ValidationError, match="contains invalid characters"):
            validate_branch_name("feature@branch")

    def test_too_long_branch(self):
        """Test branch name that is too long."""
        long_branch = "a" * 256
        with pytest.raises(ValidationError, match="too long"):
            validate_branch_name(long_branch)


class TestValidateFilePath:
    """Test validate_file_path function."""

    def test_valid_relative_path(self):
        """Test valid relative path."""
        path = "relative/path/file.txt"
        result = validate_file_path(path)
        assert result == path

    def test_empty_path(self):
        """Test empty file path."""
        with pytest.raises(ValidationError, match="File path cannot be empty"):
            validate_file_path("")

    def test_path_with_path_traversal(self):
        """Test path with traversal."""
        with pytest.raises(ValidationError, match="contains '..'"):
            validate_file_path("../etc/passwd")

    def test_path_with_dangerous_chars(self):
        """Test path with dangerous characters."""
        with pytest.raises(ValidationError, match="contains invalid characters"):
            validate_file_path("file;rm -rf /")

    def test_absolute_path_not_allowed(self):
        """Test absolute path when not allowed."""
        with pytest.raises(ValidationError, match="Absolute paths are not allowed"):
            validate_file_path("/absolute/path")

    def test_absolute_path_allowed(self):
        """Test absolute path when allowed."""
        path = "/absolute/path"
        result = validate_file_path(path, allow_absolute=True)
        assert result == path


class TestSanitizeCommandArgs:
    """Test sanitize_command_args function."""

    def test_valid_args(self):
        """Test valid command arguments."""
        args = ["git", "clone", "repo"]
        result = sanitize_command_args(args)
        assert result == args

    def test_non_list_input(self):
        """Test non-list input."""
        with pytest.raises(ValidationError, match="must be a list"):
            sanitize_command_args("not a list")

    def test_non_string_arg(self):
        """Test non-string argument."""
        with pytest.raises(ValidationError, match="must be strings"):
            sanitize_command_args(["git", 123])

    def test_dangerous_args(self):
        """Test arguments with dangerous characters."""
        with pytest.raises(ValidationError, match="dangerous characters"):
            sanitize_command_args(["git", "clone;rm -rf /"])