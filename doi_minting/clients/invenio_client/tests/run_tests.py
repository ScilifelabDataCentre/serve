#!/usr/bin/env python3
"""
Script to run all tests.
"""
import sys

import pytest

if __name__ == "__main__":
    # Run tests with coverage if available
    try:
        import coverage  # type: ignore

        cov = coverage.Coverage()
        cov.start()

        exit_code = pytest.main(["-xvs", "--tb=short", "tests/"])

        cov.stop()
        cov.save()

        # Generate coverage report
        print("\n" + "=" * 60)
        print("Coverage Report:")
        print("=" * 60)
        cov.report(show_missing=True)

        sys.exit(exit_code)
    except ImportError:
        # coverage not installed, run tests without it
        print("Warning: coverage module not installed. Running tests without coverage.")
        sys.exit(pytest.main(["-xvs", "--tb=short", "tests/"]))
