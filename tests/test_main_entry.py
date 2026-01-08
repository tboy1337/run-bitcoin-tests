"""Test the main entry point."""

import run_bitcoin_tests.__main__


class TestMainEntry:
    """Test the main entry point (__main__.py)."""

    def test_main_module_import(self):
        """Test that the __main__ module can be imported."""
        # Simply importing the __main__ module should execute the import statement
        # This should cover line 3 in __main__.py
        assert hasattr(run_bitcoin_tests.__main__, 'main')
        # Verify it's callable
        assert callable(run_bitcoin_tests.__main__.main)