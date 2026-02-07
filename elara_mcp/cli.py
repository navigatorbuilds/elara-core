"""
Elara CLI — bootstrap and run the MCP server.

Usage:
    elara init [--force]     Create ~/.elara/ with default configs
    elara serve              Start MCP server (stdio)
    elara --data-dir PATH    Override data directory
"""

import argparse
import json
import sys
from pathlib import Path


def _init(data_dir: Path, force: bool = False) -> None:
    """Bootstrap a fresh Elara data directory."""
    from core.paths import configure

    paths = configure(data_dir)

    if paths.data_dir.exists() and not force:
        print(f"Elara data directory already exists: {paths.data_dir}")
        print("Use --force to reinitialize.")
        return

    paths.ensure_dirs()

    # Create default state file
    if not paths.state_file.exists() or force:
        default_state = {
            "valence": 0.55,
            "energy": 0.5,
            "openness": 0.65,
            "session_active": False,
            "flags": {},
            "imprints": [],
        }
        paths.state_file.write_text(json.dumps(default_state, indent=2))

    # Create default presence file
    if not paths.presence_file.exists() or force:
        default_presence = {
            "last_ping": None,
            "session_start": None,
            "is_present": False,
            "total_sessions": 0,
            "total_seconds": 0,
        }
        paths.presence_file.write_text(json.dumps(default_presence, indent=2))

    # Create default feeds config
    if not paths.feeds_config.exists() or force:
        paths.feeds_config.write_text(json.dumps({"feeds": {}}, indent=2))

    # Create default goals file
    if not paths.goals_file.exists() or force:
        paths.goals_file.write_text("[]")

    # Create default corrections file
    if not paths.corrections_file.exists() or force:
        paths.corrections_file.write_text("[]")

    print(f"Elara initialized at {paths.data_dir}")
    print()
    print("Next steps:")
    print("  1. Add Elara to your MCP client:")
    print("     claude mcp add elara -- elara serve")
    print()
    print("  2. (Optional) Create a persona in your CLAUDE.md:")
    print("     See examples/CLAUDE.md.example for a template")


def _serve(data_dir: Path) -> None:
    """Start the MCP server over stdio."""
    from core.paths import configure

    configure(data_dir)

    from elara_mcp.server import mcp
    mcp.run()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="elara",
        description="Elara — persistent presence and memory for AI assistants",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Override data directory (default: $ELARA_DATA_DIR or ~/.elara/)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    init_parser = sub.add_parser("init", help="Bootstrap Elara data directory")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing files")

    # serve
    sub.add_parser("serve", help="Start MCP server (stdio)")

    args = parser.parse_args()

    # Resolve data dir: --data-dir flag → env → default
    if args.data_dir:
        data_dir = args.data_dir.expanduser().resolve()
    else:
        import os
        env = os.environ.get("ELARA_DATA_DIR")
        if env:
            data_dir = Path(env).expanduser().resolve()
        else:
            data_dir = Path.home() / ".elara"

    if args.command == "init":
        _init(data_dir, force=args.force)
    elif args.command == "serve":
        _serve(data_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
