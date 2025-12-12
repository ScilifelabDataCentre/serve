# Invenio Client Tests

This directory contains unit tests for the Invenio client library.

## Test Structure

- `conftest.py` - Shared fixtures and configuration
- `test_session.py` - Tests for session creation and configuration
- `test_http_client.py` - Tests for HTTP client wrappers
- `test_tls.py` - Tests for TLS/SSL verification helpers
- `test_invenio_client.py` - Main tests for InvenioClient class
- `test_integration.py` - Integration tests for complete workflows
- `test_examples.py` - Tests that verify the example code works correctly
- `run_tests.py` - Script to run all tests with coverage

## Running Tests

To run the tests, install the test dependencies:

```bash
pip install pytest pytest-mock responses pytest-cov

### Using pytest directly:
```bash
# Run all tests
python -m pytest itests/ -v

# Run with coverage report
python -m pytest tests/ --cov=invenio_client --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_http_client.py -v