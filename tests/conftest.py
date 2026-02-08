# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

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
