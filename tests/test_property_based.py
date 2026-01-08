"""Property-based tests for the run-bitcoin-tests package using Hypothesis."""

import subprocess
from unittest.mock import Mock, patch

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from run_bitcoin_tests.main import print_colored, run_command


class TestPrintColoredHypothesis:
    """Property-based tests for print_colored function."""

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        message=st.text(),
        color=st.sampled_from(["RED", "GREEN", "YELLOW", "CYAN", "WHITE", ""]),
        bright=st.booleans()
    )
    def test_print_colored_various_inputs(self, message, color, bright, capsys):
        """Test print_colored with various text inputs, colors, and bright settings."""
        print_colored(message, color, bright)
        captured = capsys.readouterr()

        # The message should appear in the output
        assert message in captured.out


class TestRunCommandHypothesis:
    """Property-based tests for run_command function."""

    @given(
        command=st.lists(st.text(min_size=1), min_size=1, max_size=5),
        description=st.text()
    )
    def test_run_command_various_commands(self, command, description):
        """Test run_command with various command lists and descriptions."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = run_command(command, description)

            assert result == mock_result
            mock_run.assert_called_once_with(
                command,
                capture_output=False,
                text=True,
                check=False
            )


class TestArgumentsHypothesis:
    """Property-based tests for argument parsing."""

    @given(
        repo_url=st.from_regex(r"https?://[^\s/$.?#].[^\s]*", fullmatch=True),
        branch=st.text(min_size=1, max_size=50).filter(lambda x: x.strip() == x and len(x) > 0 and not x.startswith('-'))
    )
    def test_parse_arguments_various_urls_and_branches(self, repo_url, branch):
        """Test argument parsing with various valid URLs and branch names."""
        from run_bitcoin_tests.main import parse_arguments
        from run_bitcoin_tests.validation import ValidationError

        test_args = ["script.py", "-r", repo_url, "-b", branch]

        with patch("sys.argv", test_args):
            try:
                args = parse_arguments()
                # If validation passes, URLs should be validated
                from run_bitcoin_tests.validation import validate_git_url, validate_branch_name
                expected_url = validate_git_url(repo_url)
                expected_branch = validate_branch_name(branch)
                assert args.repo_url == expected_url
                assert args.branch == expected_branch
            except SystemExit:
                # Validation failed, which is expected for some generated inputs
                # This is normal behavior - not all generated inputs will pass validation
                pass


class TestCloneRepoHypothesis:
    """Property-based tests for repository cloning."""

    @given(
        repo_url=st.from_regex(r"https?://[^\s/$.?#].[^\s]*", fullmatch=True),
        branch=st.text(min_size=1, max_size=50).filter(lambda x: x.strip() == x and len(x) > 0)
    )
    def test_clone_bitcoin_repo_various_inputs(self, repo_url, branch):
        """Test clone_bitcoin_repo with various repository URLs and branches."""
        from run_bitcoin_tests.main import clone_bitcoin_repo

        mock_result = Mock()
        mock_result.returncode = 0

        with patch("run_bitcoin_tests.main.Path") as mock_path, \
             patch("run_bitcoin_tests.main.run_command", return_value=mock_result) as mock_run:

            # Setup path mock to indicate bitcoin directory doesn't exist
            mock_bitcoin_path = Mock()
            mock_bitcoin_path.exists.return_value = False
            mock_path.return_value = mock_bitcoin_path

            clone_bitcoin_repo(repo_url, branch)

            # Verify git clone was called with correct parameters
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "git"
            assert args[1] == "clone"
            assert args[2] == "--depth"
            assert args[3] == "1"
            assert args[4] == "--branch"
            assert args[5] == branch
            assert args[6] == repo_url
            assert args[7] == "bitcoin"


class TestPrerequisitesHypothesis:
    """Property-based tests for prerequisites checking."""

    @given(
        repo_url=st.from_regex(r"https?://[^\s/$.?#].[^\s]*", fullmatch=True),
        branch=st.text(min_size=1, max_size=50).filter(lambda x: x.strip() == x and len(x) > 0)
    )
    def test_check_prerequisites_various_inputs(self, repo_url, branch):
        """Test check_prerequisites with various repository URLs and branches."""
        from run_bitcoin_tests.main import check_prerequisites

        with patch("run_bitcoin_tests.main.clone_bitcoin_repo") as mock_clone, \
             patch("run_bitcoin_tests.main.Path") as mock_path:

            # Setup path mock to indicate all required files exist
            def path_side_effect(path_str):
                mock_file = Mock()
                mock_file.exists.return_value = True
                return mock_file

            mock_path.side_effect = path_side_effect

            check_prerequisites(repo_url, branch)

            # Verify clone was called with the provided parameters
            mock_clone.assert_called_once_with(repo_url, branch)