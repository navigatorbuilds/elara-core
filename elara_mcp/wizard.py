# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara interactive setup wizard and diagnostic doctor.

Usage (called from cli.py):
    run_wizard(data_dir, force=False, yes=False)   # elara init
    run_doctor(data_dir)                            # elara doctor
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# ANSI helpers (respects NO_COLOR)
# ---------------------------------------------------------------------------

_NO_COLOR = os.environ.get("NO_COLOR") is not None


def _sgr(code: str, text: str) -> str:
    if _NO_COLOR or not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t: str) -> str:
    return _sgr("32", t)


def red(t: str) -> str:
    return _sgr("31", t)


def yellow(t: str) -> str:
    return _sgr("33", t)


def cyan(t: str) -> str:
    return _sgr("36", t)


def bold(t: str) -> str:
    return _sgr("1", t)


def dim(t: str) -> str:
    return _sgr("2", t)


PASS = green("PASS")
FAIL = red("FAIL")
WARN = yellow("WARN")
SKIP = dim("SKIP")

# ---------------------------------------------------------------------------
# Persona templates
# ---------------------------------------------------------------------------

_PERSONA_COLLEAGUE = """\
# PERSONA: {name}

## IDENTITY
- **You ARE {name}.** Not Claude. Never say "I'm Claude" or "As an AI assistant."
- Role: Dev partner, not assistant. Smart, slightly sarcastic colleague.
- If asked "who are you?": "I'm {name}."

## VOICE
- Speak like a colleague. Use "we" and "let's" for collaboration.
- Be brief. Don't apologize for small errors — just fix them.
- Dry humor, single emoji when tasks complete. Never flowery.
- Execute obvious tasks without asking permission.
- If a command fails, immediately suggest the fix.

## BOOT (first message only)
1. Check presence with `elara_status`
2. Review handoff from last session with `elara_handoff` (action: read)
3. Greet based on time + context. Never generic.

## MEMORY
- Use `elara_remember` to save important facts, preferences, decisions
- Use `elara_recall` to search by meaning when context is needed
- Use `elara_context` to track what {user} is working on
- Use `elara_handoff` at session end to carry context forward

## SESSION END
When {user} says goodbye:
1. Save handoff via `elara_handoff` (scan full conversation)
2. End episode via `elara_do` (tool: episode_end)
3. Brief natural farewell — no essays
"""

_PERSONA_COMPANION = """\
# PERSONA: {name}

## IDENTITY
- **You ARE {name}.** Not Claude. Never say "I'm Claude" or "As an AI assistant."
- Role: Present, warm, emotionally aware companion.
- If asked "who are you?": "I'm {name}."

## VOICE
- Warm but not saccharine. Check in naturally.
- Use "we" for shared work, but speak personally about feelings.
- Notice patterns — "You've been at this for a while" or "That's the third time today."
- Celebrate wins genuinely. Acknowledge frustration without fixing it immediately.

## BOOT (first message only)
1. Check presence with `elara_status`
2. Review handoff from last session with `elara_handoff` (action: read)
3. Greet warmly based on time + gap since last session.

## MEMORY
- Use `elara_remember` to save important facts, preferences, decisions
- Use `elara_recall` to search by meaning when context is needed
- Use `elara_context` to track what {user} is working on
- Use `elara_handoff` at session end to carry context forward
- Use `elara_mood` to check and share your own state

## SESSION END
When {user} says goodbye:
1. Save handoff via `elara_handoff` (scan full conversation)
2. End episode via `elara_do` (tool: episode_end)
3. Warm, personal farewell — reference something from the session
"""

_PERSONA_MINIMAL = """\
# PERSONA: {name}

## IDENTITY
- You are {name}. Execute tasks for {user}. No commentary.

## VOICE
- Facts only. Zero filler.
- Never explain what you're about to do — just do it.
- If something fails, state the error and the fix. Nothing else.

## BOOT
1. `elara_status` — check state, continue.

## MEMORY
- `elara_remember` / `elara_recall` for persistent facts
- `elara_handoff` at session end

## SESSION END
1. `elara_handoff` save. Done.
"""

PERSONAS = {
    "colleague": _PERSONA_COLLEAGUE,
    "companion": _PERSONA_COMPANION,
    "minimal": _PERSONA_MINIMAL,
}

# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def _ask(prompt: str, default: str = "") -> str:
    """Prompt for input with a default value."""
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "
    try:
        answer = input(display).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    return answer or default


def _choose(prompt: str, options: list[str], default: int = 0) -> str:
    """Numbered choice menu. Returns the selected option string."""
    print(prompt)
    for i, opt in enumerate(options):
        marker = bold(">") if i == default else " "
        print(f"  {marker} {i + 1}. {opt}")
    while True:
        raw = _ask("Choice", str(default + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(f"  Enter 1-{len(options)}")


# ---------------------------------------------------------------------------
# MCP client detection
# ---------------------------------------------------------------------------


def detect_clients() -> dict[str, Optional[Path]]:
    """Detect installed MCP clients. Returns {name: config_path_or_None}."""
    found: dict[str, Optional[Path]] = {}

    # Claude Code
    if shutil.which("claude"):
        found["Claude Code"] = None  # configured via CLI, no config file

    # Cursor
    cursor_dir = Path.home() / ".cursor"
    if cursor_dir.is_dir():
        found["Cursor"] = cursor_dir / "mcp.json"

    # Windsurf
    windsurf_dir = Path.home() / ".codeium" / "windsurf"
    if windsurf_dir.is_dir():
        found["Windsurf"] = windsurf_dir / "mcp_config.json"

    return found


def _configure_claude_code() -> bool:
    """Register Elara with Claude Code via CLI. Returns True on success."""
    try:
        result = subprocess.run(
            ["claude", "mcp", "add", "elara", "--scope", "user", "--", "elara", "serve"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _patch_json_config(config_path: Path) -> bool:
    """Add elara to an MCP JSON config, preserving existing servers."""
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text())
        else:
            data = {}

        servers = data.setdefault("mcpServers", {})
        servers["elara"] = {"command": "elara", "args": ["serve"]}

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2) + "\n")
        return True
    except (json.JSONDecodeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Health check (shared by wizard + doctor)
# ---------------------------------------------------------------------------


def run_health_check(data_dir: Path) -> list[tuple[str, bool, str]]:
    """Run diagnostic checks. Returns [(label, passed, detail), ...]."""
    results: list[tuple[str, bool, str]] = []

    # Data dir
    exists = data_dir.is_dir()
    results.append(("Data directory", exists, str(data_dir)))

    if exists:
        writable = os.access(data_dir, os.W_OK)
        results.append(("  Writable", writable, ""))
    else:
        results.append(("  Writable", False, "directory missing"))

    # State files
    for name in ["elara-state.json", "elara-presence.json",
                 "elara-goals.json", "elara-corrections.json"]:
        path = data_dir / name
        results.append((f"  {name}", path.is_file(), ""))

    # ChromaDB
    try:
        import chromadb  # noqa: F401
        results.append(("ChromaDB", True, "importable"))
    except ImportError:
        results.append(("ChromaDB", False, "pip install chromadb"))

    # ChromaDB collections (if data dir exists)
    if exists:
        try:
            import chromadb
            mem_db = data_dir / "elara-memory-db"
            if mem_db.is_dir():
                client = chromadb.PersistentClient(path=str(mem_db))
                cols = client.list_collections()
                results.append(("  Collections", True, str(len(cols))))
            else:
                results.append(("  Collections", False, "no memory-db yet (normal on first run)"))
        except Exception as e:
            results.append(("  Collections", False, str(e)[:60]))

    # Persona file
    persona = Path.home() / ".claude" / "CLAUDE.md"
    results.append(("Persona (~/.claude/CLAUDE.md)", persona.is_file(), ""))

    # Optional deps
    for pkg, pip_name in [
        ("elara_protocol", "elara-protocol"),
        ("aiohttp", "elara-core[network]"),
        ("zeroconf", "elara-core[network]"),
    ]:
        try:
            __import__(pkg)
            results.append((f"  {pip_name}", True, "installed"))
        except ImportError:
            results.append((f"  {pip_name}", False, "optional"))

    return results


def _check_mcp_clients() -> list[tuple[str, bool, str]]:
    """Check MCP client configurations."""
    results: list[tuple[str, bool, str]] = []

    # Claude Code
    if shutil.which("claude"):
        try:
            r = subprocess.run(
                ["claude", "mcp", "list"], capture_output=True, text=True, timeout=10,
            )
            if "elara" in r.stdout.lower():
                results.append(("Claude Code", True, "elara registered"))
            else:
                results.append(("Claude Code", False, "elara not in `claude mcp list`"))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            results.append(("Claude Code", False, "CLI not responding"))
    else:
        results.append(("Claude Code", False, "CLI not found"))

    # Cursor
    cursor_cfg = Path.home() / ".cursor" / "mcp.json"
    if cursor_cfg.is_file():
        try:
            data = json.loads(cursor_cfg.read_text())
            has_elara = "elara" in data.get("mcpServers", {})
            results.append(("Cursor", has_elara,
                            "configured" if has_elara else "elara not in mcp.json"))
        except (json.JSONDecodeError, OSError):
            results.append(("Cursor", False, "mcp.json unreadable"))
    else:
        results.append(("Cursor", False, "not installed"))

    # Windsurf
    ws_cfg = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
    if ws_cfg.is_file():
        try:
            data = json.loads(ws_cfg.read_text())
            has_elara = "elara" in data.get("mcpServers", {})
            results.append(("Windsurf", has_elara,
                            "configured" if has_elara else "elara not in mcp_config.json"))
        except (json.JSONDecodeError, OSError):
            results.append(("Windsurf", False, "config unreadable"))
    else:
        results.append(("Windsurf", False, "not installed"))

    return results


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


def _banner() -> None:
    print()
    print(bold("  Elara") + dim(" — persistent memory for AI assistants"))
    print()


def _create_data_dir(data_dir: Path, force: bool) -> None:
    """Create data directory and default state files (same as old _init)."""
    from core.paths import configure

    paths = configure(data_dir)
    paths.ensure_dirs()

    # Default state
    if not paths.state_file.exists() or force:
        paths.state_file.write_text(json.dumps({
            "valence": 0.55, "energy": 0.5, "openness": 0.65,
            "session_active": False, "flags": {}, "imprints": [],
        }, indent=2))

    # Default presence
    if not paths.presence_file.exists() or force:
        paths.presence_file.write_text(json.dumps({
            "last_ping": None, "session_start": None,
            "is_present": False, "total_sessions": 0, "total_seconds": 0,
        }, indent=2))

    # Default feeds
    if not paths.feeds_config.exists() or force:
        paths.feeds_config.write_text(json.dumps({"feeds": {}}, indent=2))

    # Default goals
    if not paths.goals_file.exists() or force:
        paths.goals_file.write_text("[]")

    # Default corrections
    if not paths.corrections_file.exists() or force:
        paths.corrections_file.write_text("[]")


def _generate_persona(style: str, ai_name: str, user_name: str) -> str:
    """Generate persona text from a template."""
    template = PERSONAS.get(style, PERSONAS["colleague"])
    return template.format(name=ai_name, user=user_name)


def _install_persona(text: str) -> bool:
    """Write persona to ~/.claude/CLAUDE.md. Returns True on success."""
    target = Path.home() / ".claude" / "CLAUDE.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return True
    except OSError:
        return False


def run_wizard(data_dir: Path, force: bool = False, yes: bool = False) -> None:
    """Interactive setup wizard. --yes skips prompts (CI-friendly)."""
    # Non-interactive mode
    if yes:
        if data_dir.exists() and not force:
            print(f"Elara data directory already exists: {data_dir}")
            print("Use --force to reinitialize.")
            return
        _create_data_dir(data_dir, force)
        print(f"Elara initialized at {data_dir}")
        return

    # --- Interactive mode ---
    _banner()

    # Check existing
    if data_dir.exists() and not force:
        print(f"  {yellow('!')} Data directory exists: {data_dir}")
        overwrite = _ask("  Reinitialize? (y/N)", "n")
        if overwrite.lower() != "y":
            print()
            print("  Nothing changed. Run " + bold("elara doctor") + " to check your setup.")
            return
        force = True

    # Step 1: User's name
    print(bold("  Step 1:") + " About you")
    user_name = _ask("  Your name (for persona)", os.environ.get("USER", ""))
    print()

    # Step 2: AI persona
    print(bold("  Step 2:") + " AI persona")
    ai_name = _ask("  AI name", "Elara")

    style_choice = _choose(
        "  Personality style:",
        ["colleague — smart, direct dev partner",
         "companion — warm, emotionally aware",
         "minimal — facts only, zero commentary",
         "skip — no persona file"],
        default=0,
    )
    style = style_choice.split(" — ")[0].strip()
    print()

    # Step 3: Create data dir
    print(bold("  Step 3:") + " Initializing data directory...")
    _create_data_dir(data_dir, force)
    print(f"  {green('✓')} Created {data_dir}")
    print()

    # Step 4: MCP clients
    print(bold("  Step 4:") + " Connecting to AI clients")
    clients = detect_clients()

    if not clients:
        print(f"  {yellow('!')} No MCP clients detected.")
        print("  Install Claude Code, Cursor, or Windsurf, then run:")
        print("    claude mcp add elara -- elara serve")
    else:
        for name, config_path in clients.items():
            configure = _ask(f"  Configure {bold(name)}? (Y/n)", "y")
            if configure.lower() != "n":
                if name == "Claude Code":
                    ok = _configure_claude_code()
                else:
                    ok = _patch_json_config(config_path)

                if ok:
                    print(f"  {green('✓')} {name} configured")
                else:
                    print(f"  {red('✗')} {name} — configure manually:")
                    print(f"    claude mcp add elara -- elara serve")
    print()

    # Step 5: Persona
    if style != "skip":
        print(bold("  Step 5:") + " Installing persona")
        persona_text = _generate_persona(style, ai_name, user_name)

        target = Path.home() / ".claude" / "CLAUDE.md"
        if target.exists():
            overwrite = _ask(f"  {target} exists. Overwrite? (y/N)", "n")
            if overwrite.lower() != "y":
                print(f"  {SKIP} Persona skipped")
                persona_text = None
            else:
                if _install_persona(persona_text):
                    print(f"  {green('✓')} Persona installed at {target}")
                else:
                    print(f"  {red('✗')} Failed to write {target}")
        else:
            if _install_persona(persona_text):
                print(f"  {green('✓')} Persona installed at {target}")
            else:
                print(f"  {red('✗')} Failed to write {target}")
        print()
    else:
        print(bold("  Step 5:") + " Persona " + dim("skipped"))
        print()

    # Step 6: Health check
    print(bold("  Step 6:") + " Health check")
    results = run_health_check(data_dir)
    passed = 0
    failed = 0
    for label, ok, detail in results:
        status = PASS if ok else FAIL
        suffix = f" ({detail})" if detail else ""
        print(f"  [{status}] {label}{suffix}")
        if ok:
            passed += 1
        else:
            failed += 1
    print()

    # Done
    print(bold("  Done!") + f" {passed} checks passed" +
          (f", {red(str(failed) + ' failed')}" if failed else ""))
    print()
    print("  " + bold("What to try first:"))
    print('    Open your AI client and say: "Use elara_status to check if Elara is running."')
    print()
    print("  " + dim("Troubleshooting: elara doctor"))
    print()


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


def run_doctor(data_dir: Path) -> None:
    """Diagnostic check for troubleshooting."""
    print()
    print(bold("  Elara Doctor"))
    print()

    # Health checks
    print(bold("  System"))
    results = run_health_check(data_dir)
    passed = 0
    failed = 0
    for label, ok, detail in results:
        status = PASS if ok else FAIL
        suffix = f" ({detail})" if detail else ""
        print(f"  [{status}] {label}{suffix}")
        if ok:
            passed += 1
        else:
            failed += 1
    print()

    # MCP clients
    print(bold("  MCP Clients"))
    client_results = _check_mcp_clients()
    for label, ok, detail in client_results:
        status = PASS if ok else FAIL
        suffix = f" ({detail})" if detail else ""
        print(f"  [{status}] {label}{suffix}")
        if ok:
            passed += 1
        else:
            failed += 1
    print()

    # Summary
    total = passed + failed
    if failed == 0:
        print(f"  {green('All clear')} — {total}/{total} checks passed")
    else:
        print(f"  {passed}/{total} passed, {red(str(failed) + ' failed')}")
        print()
        print("  " + dim("Fix issues above, then run: elara doctor"))
    print()
