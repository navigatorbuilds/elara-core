# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Elara Core, please report it responsibly:

**Email:** aivelikivodja@gmail.com

**Subject line:** `[SECURITY] elara-core: brief description`

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Assessment:** Within 1 week
- **Fix (if confirmed):** As soon as possible, typically within 2 weeks

## Scope

The following are in scope:
- Elara Core Python package (`elara-core` on PyPI)
- MCP tool implementations
- Data storage and retrieval (ChromaDB, JSON/JSONL files)
- Authentication flows (Gmail OAuth)

The following are **not** in scope:
- The landing pages (navigatorbuilds.com, elara.navigatorbuilds.com)
- Third-party dependencies (report those upstream)

## Data Privacy

Elara Core stores all data locally on the user's machine. No telemetry, no cloud sync, no external data transmission (except Gmail integration when explicitly configured by the user).

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.9.x   | Yes       |
| < 0.9   | No        |
