# Contributing to Elara Core

Thanks for your interest. Here's how to get started.

## Setup

```bash
git clone https://github.com/aivelikivodja-bot/elara-core.git
cd elara-core
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

All 91 tests should pass. Tests use isolated temp directories — no real data is touched.

## Project Structure

```
elara-core/
├── core/           # Core library (paths, schemas, Elara class)
├── daemon/         # State engine (mood, presence, emotions, decay)
├── elara_mcp/      # MCP server + tool definitions
│   └── tools/      # 34 tools across 11 modules
├── tests/          # Test suite (pytest)
├── docs/           # GitHub Pages site
└── pyproject.toml  # Package config
```

## Making Changes

1. **Fork the repo** and create a branch from `main`
2. **Write tests** for new functionality
3. **Run the test suite** before submitting
4. **Keep commits focused** — one logical change per commit
5. **Open a PR** with a clear description

## What to Work On

Check the [issue tracker](https://github.com/aivelikivodja-bot/elara-core/issues) for open items. Good first issues are labeled accordingly.

Areas that welcome contributions:
- **New MCP tools** — extend existing modules or propose new ones
- **Test coverage** — more edge cases, integration tests
- **Documentation** — usage examples, guides
- **Bug fixes** — check the issues

## Code Style

- Python 3.12+ (we use modern f-string syntax)
- Type hints where they add clarity
- Docstrings on public functions
- No unnecessary dependencies

## Reporting Issues

Use the [bug report](https://github.com/aivelikivodja-bot/elara-core/issues/new?template=bug_report.yml) or [feature request](https://github.com/aivelikivodja-bot/elara-core/issues/new?template=feature_request.yml) templates.

## License

By contributing, you agree that your contributions will be licensed under the BSL-1.1 license.
