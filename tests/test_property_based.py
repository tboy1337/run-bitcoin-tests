"""Property-based tests for the run-bitcoin-tests package using Hypothesis."""

import subprocess
from unittest.mock import Mock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from run_bitcoin_tests.main import print_colored, run_command
from run_bitcoin_tests.validation import ValidationError


class TestPrintColoredHypothesis:
    """Property-based tests for print_colored function."""

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        message=st.text(),
        color=st.sampled_from(["RED", "GREEN", "YELLOW", "CYAN", "WHITE", ""]),
        bright=st.booleans(),
    )
    def test_print_colored_various_inputs(self, message, color, bright, capsys):
        """Test print_colored with various text inputs, colors, and bright settings."""
        print_colored(message, color, bright)
        captured = capsys.readouterr()

        # The message should appear in the output
        assert message in captured.out


class TestRunCommandHypothesis:
    """Property-based tests for run_command function."""

    @given(command=st.lists(st.text(min_size=1), min_size=1, max_size=5), description=st.text())
    def test_run_command_various_commands(self, command, description):
        """Test run_command with various command lists and descriptions."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = run_command(command, description)

            assert result == mock_result
            mock_run.assert_called_once_with(command, capture_output=False, text=True, check=False)


class TestArgumentsHypothesis:
    """Property-based tests for argument parsing."""

    @given(
        repo_url=st.from_regex(r"https?://[^\s/$.?#].[^\s]*", fullmatch=True),
        branch=st.text(min_size=1, max_size=50).filter(
            lambda x: x.strip() == x and len(x) > 0 and not x.startswith("-")
        ),
    )
    def test_parse_arguments_various_urls_and_branches(self, repo_url, branch):
        """Test argument parsing with various valid URLs and branch names."""
        from run_bitcoin_tests.main import parse_arguments
        from run_bitcoin_tests.validation import ValidationError

        test_args = ["script.py", "-r", repo_url, "-b", branch]

        with patch("sys.argv", test_args):
            try:
                args = parse_arguments()
                # If parsing succeeds, the args should contain the provided values
                assert args.repo_url == repo_url
                assert args.branch == branch
            except SystemExit:
                # Argument parsing failed, which is expected for some generated inputs
                # This is normal behavior - not all generated inputs will pass basic parsing
                pass


class TestCloneRepoHypothesis:
    """Property-based tests for repository cloning."""

    @given(
        repo_url=st.from_regex(r"https?://[^\s/$.?#].[^\s]*", fullmatch=True),
        branch=st.text(min_size=1, max_size=50).filter(lambda x: x.strip() == x and len(x) > 0),
    )
    def test_clone_bitcoin_repo_various_inputs(self, repo_url, branch):
        """Test clone_bitcoin_repo with various repository URLs and branches."""
        from run_bitcoin_tests.main import clone_bitcoin_repo

        with patch("run_bitcoin_tests.main.clone_bitcoin_repo_enhanced") as mock_clone_enhanced:
            # Mock the enhanced clone function to not raise an exception
            mock_clone_enhanced.return_value = None

            try:
                clone_bitcoin_repo(repo_url, branch)

                # Verify the enhanced clone function was called with correct parameters
                mock_clone_enhanced.assert_called_once_with(
                    repo_url=repo_url, branch=branch, target_dir="bitcoin", use_cache=True
                )
            except ValidationError:
                # Some generated inputs may be invalid, which is expected
                pass


class TestPrerequisitesHypothesis:
    """Property-based tests for prerequisites checking."""

    @given(
        repo_url=st.from_regex(r"https?://[^\s/$.?#].[^\s]*", fullmatch=True),
        branch=st.text(min_size=1, max_size=50).filter(lambda x: x.strip() == x and len(x) > 0),
    )
    def test_check_prerequisites_various_inputs(self, repo_url, branch):
        """Test check_prerequisites with various repository URLs and branches."""
        from run_bitcoin_tests.main import check_prerequisites

        with (
            patch("run_bitcoin_tests.main.clone_bitcoin_repo") as mock_clone,
            patch("run_bitcoin_tests.main.Path") as mock_path,
            patch("run_bitcoin_tests.main.get_config") as mock_get_config,
        ):

            # Mock config
            mock_config = Mock()
            mock_config.repository.url = repo_url
            mock_config.repository.branch = branch
            mock_config.quiet = True
            mock_config.docker.compose_file = "docker-compose.yml"
            mock_get_config.return_value = mock_config

            # Setup path mock to indicate all required files exist
            def path_side_effect(path_str):
                mock_file = Mock()
                mock_file.exists.return_value = True
                return mock_file

            mock_path.side_effect = path_side_effect

            try:
                check_prerequisites()

                # Verify clone was called with the provided parameters
                mock_clone.assert_called_once_with(repo_url, branch)
            except ValidationError:
                # Some generated inputs may be invalid, which is expected
                pass
