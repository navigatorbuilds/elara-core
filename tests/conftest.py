"""Test configuration — paths isolation for tests."""

import pytest
from pathlib import Path

from core.paths import configure, reset


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path):
    """Route all Elara data to a temp directory for test isolation."""
    paths = configure(tmp_path)
    paths.ensure_dirs()
    yield paths
    reset()
