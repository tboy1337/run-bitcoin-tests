"""
Input validation utilities for the Bitcoin Core tests runner.

This module provides validation functions for repository URLs, branch names,
and other user inputs to ensure they are safe and valid before processing.
"""

import re
import urllib.parse
from typing import Optional


class ValidationError(Exception):
    """Exception raised when input validation fails."""
    pass


def validate_git_url(url: str) -> str:
    """
    Validate and normalize a Git repository URL.

    Args:
        url: The URL to validate

    Returns:
        The normalized URL

    Raises:
        ValidationError: If the URL is invalid
    """
    if not url or not url.strip():
        raise ValidationError("Repository URL cannot be empty")

    url = url.strip()

    # Check for basic URL format
    if not (url.startswith('http://') or url.startswith('https://') or url.startswith('git@')):
        raise ValidationError(
            "Repository URL must start with 'http://', 'https://', or 'git@'"
        )

    # For HTTP/HTTPS URLs, validate the structure
    if url.startswith(('http://', 'https://')):
        try:
            parsed = urllib.parse.urlparse(url)
            if not parsed.netloc:
                raise ValidationError("Repository URL must include a valid domain")

            # Check for suspicious characters that could indicate injection attempts
            if any(char in url for char in ['<', '>', '"', "'", ';', '|', '&', '$', '`']):
                raise ValidationError(
                    "Repository URL contains invalid characters"
                )

            # Ensure it looks like a Git repository URL
            path = parsed.path.lower()
            if not (path.endswith('.git') or '/bitcoin' in path or '/bitcoin-core' in path):
                # Allow any .git URL or paths that contain bitcoin-related terms
                if not path.endswith('.git'):
                    print_colored(
                        f"Warning: URL '{url}' doesn't appear to be a Git repository. "
                        "Proceeding anyway, but this might fail.",
                        Fore.YELLOW
                    )

        except Exception as e:
            raise ValidationError(f"Invalid repository URL format: {e}")

    return url


def validate_branch_name(branch: str) -> str:
    """
    Validate a Git branch name.

    Args:
        branch: The branch name to validate

    Returns:
        The validated branch name

    Raises:
        ValidationError: If the branch name is invalid
    """
    if not branch or not branch.strip():
        raise ValidationError("Branch name cannot be empty")

    branch = branch.strip()

    # Check length constraints
    if len(branch) > 255:
        raise ValidationError("Branch name is too long (maximum 255 characters)")

    # Check for dangerous characters that could be used for command injection
    dangerous_chars = ['<', '>', '"', "'", ';', '|', '&', '$', '`', '\n', '\r', '\t']
    if any(char in branch for char in dangerous_chars):
        raise ValidationError(
            "Branch name contains invalid characters: " +
            "".join(set(char for char in branch if char in dangerous_chars))
        )

    # Check for path traversal attempts
    if '..' in branch or branch.startswith('/') or branch.startswith('./') or branch.startswith('../'):
        raise ValidationError("Branch name contains invalid path components")

    # Git branch name rules (relaxed version)
    # Allow alphanumeric, hyphens, underscores, and forward slashes
    if not re.match(r'^[a-zA-Z0-9._/-]+$', branch):
        raise ValidationError(
            "Branch name contains invalid characters. "
            "Only alphanumeric characters, hyphens, underscores, dots, and forward slashes are allowed."
        )

    # Prevent branch names that look like command line options
    if branch.startswith('-'):
        raise ValidationError("Branch name cannot start with a dash (would be interpreted as a command-line option)")

    return branch


def validate_file_path(path: str, allow_absolute: bool = False) -> str:
    """
    Validate a file path for safety.

    Args:
        path: The file path to validate
        allow_absolute: Whether to allow absolute paths

    Returns:
        The validated path

    Raises:
        ValidationError: If the path is invalid
    """
    if not path or not path.strip():
        raise ValidationError("File path cannot be empty")

    path = path.strip()

    # Check for path traversal
    if '..' in path:
        raise ValidationError("File path contains '..' which is not allowed")

    # Check for dangerous characters
    dangerous_chars = ['<', '>', '"', "'", ';', '|', '&', '$', '`']
    if any(char in path for char in dangerous_chars):
        raise ValidationError("File path contains invalid characters")

    # Check if absolute path is allowed
    if not allow_absolute and path.startswith('/'):
        raise ValidationError("Absolute paths are not allowed")

    return path


def sanitize_command_args(args: list) -> list:
    """
    Sanitize command arguments to prevent injection attacks.

    Args:
        args: List of command arguments

    Returns:
        Sanitized list of arguments

    Raises:
        ValidationError: If arguments contain dangerous content
    """
    if not isinstance(args, list):
        raise ValidationError("Command arguments must be a list")

    sanitized = []
    for arg in args:
        if not isinstance(arg, str):
            raise ValidationError("All command arguments must be strings")

        # Check for shell metacharacters that could be dangerous
        dangerous_patterns = [';', '|', '&', '$', '`', '(', ')', '<', '>', '"', "'"]
        if any(pattern in arg for pattern in dangerous_patterns):
            raise ValidationError(f"Command argument contains dangerous characters: {arg}")

        sanitized.append(arg)

    return sanitized


# Import print_colored here to avoid circular imports
try:
    from .main import print_colored, Fore
except ImportError:
    # Fallback for when this module is imported directly
    def print_colored(message, color="", bright=False):
        print(message)

    class Fore:
        YELLOW = ""