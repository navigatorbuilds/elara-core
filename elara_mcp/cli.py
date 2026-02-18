# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara CLI — bootstrap, run MCP server, and Layer 1 crypto operations.

Usage:
    elara init [--force]           Create ~/.elara/ with default configs
    elara serve                    Start MCP server (stdio, lean profile)
    elara serve --profile full     Start with all 39 tool schemas
    elara serve --profile lean     Start with 7 core + elara_do (default)
    elara sign <file>              Sign a file with Dilithium3+SPHINCS+
    elara verify <proof>           Verify an .elara.proof file
    elara identity                 Show identity info
    elara dag stats                Show DAG statistics
    elara testnet                  Run 2-node testnet demo
    elara testnet --nodes 3        Run N-node testnet
    elara --data-dir PATH          Override data directory
"""

import argparse
import hashlib
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


def _serve(data_dir: Path, profile: str = "lean") -> None:
    """Start the MCP server over stdio."""
    from core.paths import configure

    configure(data_dir)

    # Set profile BEFORE importing server (which imports tool modules)
    from elara_mcp._app import set_profile
    set_profile(profile)

    from elara_mcp.server import mcp
    mcp.run()


# ---------------------------------------------------------------------------
# Layer 1 CLI commands
# ---------------------------------------------------------------------------

def _sign(data_dir: Path, file_path: str, classification: str = "SOVEREIGN") -> None:
    """Sign a file with Dilithium3 + SPHINCS+ dual signatures."""
    try:
        from elara_protocol.identity import Identity, EntityType, CryptoProfile
        from elara_protocol.record import ValidationRecord, Classification
        from elara_protocol.dag import LocalDAG
    except ImportError:
        print("Error: elara-protocol not installed.")
        print("  pip install elara-protocol")
        sys.exit(1)

    from core.paths import configure
    paths = configure(data_dir)

    source = Path(file_path)
    if not source.exists():
        print(f"Error: file not found: {source}")
        sys.exit(1)

    # Load identity
    if not paths.identity_file.exists():
        print(f"Error: no identity at {paths.identity_file}")
        print("  Run: elara init")
        sys.exit(1)

    identity = Identity.load(paths.identity_file)

    # Read file content
    content = source.read_bytes()
    content_hash = hashlib.sha3_256(content).digest()

    # Resolve classification
    try:
        cls = Classification[classification.upper()]
    except KeyError:
        print(f"Error: unknown classification '{classification}'")
        print(f"  Valid: {', '.join(c.name for c in Classification)}")
        sys.exit(1)

    # Open DAG for parent chaining
    dag = LocalDAG(paths.dag_file)
    tips = dag.tips()
    parents = [tips[-1]] if tips else []

    # Create record
    record = ValidationRecord.create(
        content=content,
        creator_public_key=identity.public_key,
        parents=parents,
        classification=cls,
        metadata={
            "artifact_type": "file",
            "filename": source.name,
            "content_hash_hex": content_hash.hex(),
            "file_size": len(content),
        },
    )

    # Dual sign
    signable = record.signable_bytes()
    record.signature = identity.sign(signable)
    if identity.profile == CryptoProfile.PROFILE_A:
        record.sphincs_signature = identity.sign_sphincs(signable)

    # Insert into DAG
    record_hash = dag.insert(record, verify_signature=True)

    # Write proof file
    wire_bytes = record.to_bytes()
    proof = {
        "record_id": record.id,
        "record_hash": record_hash,
        "content_hash": content_hash.hex(),
        "creator": identity.identity_hash,
        "classification": cls.name,
        "filename": source.name,
        "wire_bytes": wire_bytes.hex(),
    }
    proof_path = Path(f"{file_path}.elara.proof")
    proof_path.write_text(json.dumps(proof, indent=2))

    dag.close()

    print(f"Signed: {source.name}")
    print(f"  Record:  {record.id}")
    print(f"  Hash:    {record_hash[:16]}...")
    print(f"  Content: {content_hash.hex()[:16]}...")
    print(f"  Proof:   {proof_path}")


def _verify(data_dir: Path, proof_path: str) -> None:
    """Verify an .elara.proof file."""
    try:
        from elara_protocol.record import ValidationRecord
    except ImportError:
        print("Error: elara-protocol not installed.")
        print("  pip install elara-protocol")
        sys.exit(1)

    from core.paths import configure
    configure(data_dir)

    ppath = Path(proof_path)
    if not ppath.exists():
        print(f"Error: proof file not found: {ppath}")
        sys.exit(1)

    proof = json.loads(ppath.read_text())

    # Decode wire bytes
    try:
        wire_bytes = bytes.fromhex(proof["wire_bytes"])
    except (KeyError, ValueError) as e:
        print(f"Error: invalid proof file — {e}")
        sys.exit(1)

    record = ValidationRecord.from_bytes(wire_bytes)

    # Verify Dilithium3 signature
    signable = record.signable_bytes()
    try:
        import oqs
        verifier = oqs.Signature("Dilithium3")
        valid = verifier.verify(signable, record.signature, record.creator_public_key)
    except ImportError:
        print("Warning: liboqs not available, cannot verify Dilithium3 signature")
        valid = None

    # Check content hash against source file if it exists nearby
    source_path = ppath.with_suffix("").with_suffix("")  # strip .elara.proof
    if not source_path.exists():
        # Try without double suffix strip — just remove .elara.proof
        name = ppath.name
        if name.endswith(".elara.proof"):
            source_path = ppath.parent / name[: -len(".elara.proof")]

    content_match = None
    if source_path.exists():
        actual_hash = hashlib.sha3_256(source_path.read_bytes()).hexdigest()
        content_match = actual_hash == proof.get("content_hash")

    # Report
    print(f"Proof: {ppath.name}")
    print(f"  Record:    {proof.get('record_id', '?')}")
    print(f"  Creator:   {proof.get('creator', '?')[:24]}...")
    print(f"  Class:     {proof.get('classification', '?')}")

    if valid is True:
        print(f"  Signature: VALID")
    elif valid is False:
        print(f"  Signature: INVALID")
        sys.exit(1)
    else:
        print(f"  Signature: UNVERIFIED (liboqs not installed)")

    if content_match is True:
        print(f"  Content:   MATCHES {source_path.name}")
    elif content_match is False:
        print(f"  Content:   MISMATCH — file has been modified!")
        sys.exit(1)
    else:
        print(f"  Content:   source file not found (cannot verify content)")

    if valid is not False and content_match is not False:
        print("  Result:    OK")
        sys.exit(0)
    else:
        sys.exit(1)


def _identity(data_dir: Path) -> None:
    """Show identity information."""
    try:
        from elara_protocol.identity import Identity
    except ImportError:
        print("Error: elara-protocol not installed.")
        sys.exit(1)

    from core.paths import configure
    paths = configure(data_dir)

    if not paths.identity_file.exists():
        print(f"No identity found at {paths.identity_file}")
        print("  Run: elara init  (identity is generated on first MCP server start)")
        sys.exit(1)

    identity = Identity.load(paths.identity_file)

    print(f"Identity: {identity.identity_hash}")
    print(f"  Entity:  {identity.entity_type.name}")
    print(f"  Profile: {identity.profile.name}")
    print(f"  Created: {identity.created}")
    print(f"  Dilithium3 PK: {len(identity.public_key)} bytes")
    if hasattr(identity, 'sphincs_public_key') and identity.sphincs_public_key:
        print(f"  SPHINCS+  PK: {len(identity.sphincs_public_key)} bytes")


def _dag_stats(data_dir: Path) -> None:
    """Show DAG statistics."""
    try:
        from elara_protocol.dag import LocalDAG
    except ImportError:
        print("Error: elara-protocol not installed.")
        sys.exit(1)

    from core.paths import configure
    paths = configure(data_dir)

    if not paths.dag_file.exists():
        print(f"No DAG found at {paths.dag_file}")
        sys.exit(1)

    dag = LocalDAG(paths.dag_file)
    stats = dag.stats()
    tips = dag.tips()

    print(f"DAG: {paths.dag_file}")
    print(f"  Records: {stats.get('record_count', 0)}")
    print(f"  Edges:   {stats.get('edge_count', 0)}")
    print(f"  Tips:    {len(tips)}")
    print(f"  Roots:   {stats.get('root_count', 0)}")
    if stats.get("oldest"):
        print(f"  Oldest:  {stats['oldest']}")
    if stats.get("newest"):
        print(f"  Newest:  {stats['newest']}")

    dag.close()


# ---------------------------------------------------------------------------
# Testnet
# ---------------------------------------------------------------------------

def _testnet(nodes: int = 2, port_base: int = 9473, verbose: bool = False) -> None:
    """Run the Layer 2 testnet demo."""
    try:
        import asyncio
        from scripts.testnet import run_testnet
    except ImportError:
        print("Error: testnet script not found or dependencies missing.")
        print("  pip install elara-core[network] elara-protocol")
        sys.exit(1)

    success = asyncio.run(run_testnet(
        num_nodes=nodes, port_base=port_base, verbose=verbose,
    ))
    sys.exit(0 if success else 1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="elara",
        description="Elara — persistent presence and memory for AI assistants",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        dest="top_data_dir",
        help="Override data directory (default: $ELARA_DATA_DIR or ~/.elara/)",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    init_parser = sub.add_parser("init", help="Bootstrap Elara data directory")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    init_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                             help="Override data directory (default: $ELARA_DATA_DIR or ~/.elara/)")

    # serve
    serve_parser = sub.add_parser("serve", help="Start MCP server (stdio)")
    serve_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                              help="Override data directory (default: $ELARA_DATA_DIR or ~/.elara/)")
    serve_parser.add_argument("--profile", choices=["lean", "full"], default=None,
                              help="Tool profile: lean (8 schemas, default) or full (all 39+1 schemas)")

    # sign
    sign_parser = sub.add_parser("sign", help="Sign a file with Layer 1 crypto")
    sign_parser.add_argument("file", help="File to sign")
    sign_parser.add_argument("--classification", default="SOVEREIGN",
                             help="Classification level (default: SOVEREIGN)")
    sign_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                             help="Override data directory")

    # verify
    verify_parser = sub.add_parser("verify", help="Verify an .elara.proof file")
    verify_parser.add_argument("proof", help="Proof file to verify")
    verify_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                               help="Override data directory")

    # identity
    id_parser = sub.add_parser("identity", help="Show identity information")
    id_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                           help="Override data directory")

    # dag
    dag_parser = sub.add_parser("dag", help="DAG operations")
    dag_sub = dag_parser.add_subparsers(dest="dag_command")
    dag_stats_parser = dag_sub.add_parser("stats", help="Show DAG statistics")
    dag_stats_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                                  help="Override data directory")
    dag_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                            help="Override data directory")

    # testnet
    testnet_parser = sub.add_parser("testnet", help="Run 2-node testnet demo")
    testnet_parser.add_argument("--nodes", type=int, default=2,
                                help="Number of nodes (default: 2)")
    testnet_parser.add_argument("--port-base", type=int, default=9473,
                                help="Starting port (default: 9473)")
    testnet_parser.add_argument("--verbose", "-v", action="store_true",
                                help="Detailed output")

    args = parser.parse_args()

    # Resolve data dir: subcommand flag → top-level flag → env → default
    import os
    raw = getattr(args, "sub_data_dir", None) or getattr(args, "top_data_dir", None)
    if raw:
        data_dir = raw.expanduser().resolve()
    else:
        env = os.environ.get("ELARA_DATA_DIR")
        if env:
            data_dir = Path(env).expanduser().resolve()
        else:
            data_dir = Path.home() / ".elara"

    if args.command == "init":
        _init(data_dir, force=args.force)
    elif args.command == "serve":
        # Resolve profile: CLI arg → env var → default "lean"
        profile = args.profile or os.environ.get("ELARA_PROFILE", "lean")
        _serve(data_dir, profile=profile)
    elif args.command == "sign":
        _sign(data_dir, args.file, args.classification)
    elif args.command == "verify":
        _verify(data_dir, args.proof)
    elif args.command == "identity":
        _identity(data_dir)
    elif args.command == "testnet":
        _testnet(args.nodes, args.port_base, args.verbose)
    elif args.command == "dag":
        if getattr(args, "dag_command", None) == "stats":
            _dag_stats(data_dir)
        else:
            dag_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
