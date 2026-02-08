# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Root conftest — prevent pytest from importing root __init__.py as a package."""

collect_ignore = ["__init__.py"]
