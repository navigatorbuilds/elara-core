"""Root conftest — prevent pytest from importing root __init__.py as a package."""

collect_ignore = ["__init__.py"]
