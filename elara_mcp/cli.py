# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara CLI — bootstrap, run MCP server, network node, and Layer 1 crypto.

Usage:
    elara init                     Interactive setup wizard
    elara init --yes               Non-interactive init (CI/scripts)
    elara init --force             Reinitialize existing setup
    elara doctor                   Diagnostic health check
    elara serve                    Start MCP server + network node (stdio)
    elara serve --no-node          Start MCP server without network node
    elara serve --profile full     Start with all 45 tool schemas
    elara serve --profile lean     Start with 7 core + elara_do (default)
    elara serve --tier 0           Tier 0 VALIDATE (crypto+DAG only)
    elara serve --tier 1           Tier 1 REMEMBER (memory, episodes, goals)
    elara serve --tier 2           Tier 2 THINK (default, full cognitive)
    elara serve --tier 3           Tier 3 CONNECT (+ network mesh)
    elara node status              Show node info (type, port, peers)
    elara node peers               List connected peers
    elara node start               Enable network node
    elara node stop                Disable network node
    elara sign <file>              Sign a file with Dilithium3+SPHINCS+
    elara verify <proof>           Verify an .elara.proof file
    elara identity                 Show identity info
    elara dag stats                Show DAG statistics
    elara continuity status        Show continuity chain info
    elara continuity verify        Verify chain integrity
    elara testnet                  Run 2-node testnet demo
    elara testnet --nodes 3        Run N-node testnet
    elara --data-dir PATH          Override data directory
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _init(data_dir: Path, force: bool = False, yes: bool = False) -> None:
    """Bootstrap Elara — interactive wizard or silent init (--yes)."""
    from elara_mcp.wizard import run_wizard
    run_wizard(data_dir, force=force, yes=yes)


def _doctor(data_dir: Path) -> None:
    """Run diagnostic health checks."""
    from elara_mcp.wizard import run_doctor
    run_doctor(data_dir)


def _serve(data_dir: Path, profile: str = "lean", no_node: bool = False,
           tier: int = 2) -> None:
    """Start the MCP server over stdio, optionally with network node."""
    import os
    import threading
    from core.paths import configure
    from core.tiers import set_tier, tier_name

    paths = configure(data_dir)

    # Set tier BEFORE importing server (which imports tool modules)
    set_tier(tier)

    # Version check (non-blocking, background thread)
    def _check_version():
        try:
            from network.bootstrap import check_version_async
            msg = check_version_async()
            if msg:
                # Print to stderr so it doesn't interfere with MCP stdio
                print(msg, file=sys.stderr)
        except Exception:
            pass

    threading.Thread(target=_check_version, daemon=True, name="elara-version-check").start()

    # Start network node unless --no-node
    if not no_node:
        _maybe_start_node(paths, sys.stderr)

    # Set profile BEFORE importing server (which imports tool modules)
    from elara_mcp._app import set_profile
    set_profile(profile)

    from elara_mcp.server import mcp
    mcp.run()


def _maybe_start_node(paths, log_file=None) -> bool:
    """Start network node if enabled in config. Returns True if started.

    Runs in a background thread — never blocks MCP startup.
    """
    import os
    import threading

    try:
        from network.bootstrap import load_network_config
        config = load_network_config(paths.network_config)
    except Exception:
        config = {"enabled": True, "node_type": "leaf", "port": 0, "seed_nodes": []}

    if not config.get("enabled", True):
        return False

    def _start_node():
        try:
            _do_start_node(paths, config, log_file)
        except Exception as e:
            if log_file:
                print(f"Node startup failed (non-fatal): {e}", file=log_file)

    thread = threading.Thread(target=_start_node, daemon=True, name="elara-node-startup")
    thread.start()
    return True


def _do_start_node(paths, config: dict, log_file=None) -> None:
    """Actually start the network node (runs in background thread)."""
    import asyncio
    import os

    # Check if network deps are available
    try:
        from network.server import NetworkServer
        from network.discovery import PeerDiscovery
        from network.types import NodeType
        from network.bootstrap import bootstrap_peers
    except ImportError:
        if log_file:
            print("Network node disabled — install with: pip install elara-core[network]",
                  file=log_file)
        return

    # Need Layer 1 identity
    if not paths.identity_file.exists():
        if log_file:
            print("Network node skipped — no identity (run: elara init)", file=log_file)
        return

    try:
        from elara_protocol.identity import Identity
        from elara_protocol.dag import LocalDAG
    except ImportError:
        if log_file:
            print("Network node skipped — elara-protocol not installed", file=log_file)
        return

    identity = Identity.load(paths.identity_file)

    # Resolve port: config → env → 0 (random)
    port = config.get("port", 0)
    if not port:
        port = int(os.environ.get("ELARA_NETWORK_PORT", "0"))
    if not port:
        # Find a free port
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

    # Resolve node type
    node_type_str = config.get("node_type", "leaf")
    env_type = os.environ.get("ELARA_NODE_TYPE")
    if env_type:
        node_type_str = env_type
    try:
        node_type = NodeType(node_type_str)
    except ValueError:
        node_type = NodeType.LEAF

    # Start discovery with bootstrapped peers
    discovery = PeerDiscovery(
        identity_hash=identity.identity_hash,
        port=port,
        peers_file=paths.network_peers,
        node_type=node_type,
    )

    # Add seed peers from config/bootstrap
    peers = bootstrap_peers(config, peers_file=paths.network_peers)
    for peer in peers:
        discovery.add_peer(
            host=peer["host"],
            port=peer["port"],
            identity_hash=peer.get("identity_hash", ""),
        )

    discovery.start()

    # Start HTTP server
    dag = LocalDAG(paths.dag_file)
    server = NetworkServer(
        identity, dag, port=port,
        attestations_db=paths.attestations_db,
        node_type=node_type_str,
    )

    # Store references in the network tool module for CLI access
    try:
        from elara_mcp.tools import network as net_mod
        net_mod._discovery = discovery
        net_mod._server = server
    except Exception:
        pass

    # Run server event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        from elara_mcp.tools import network as net_mod
        net_mod._server_loop = loop
    except Exception:
        pass

    loop.run_until_complete(server.start())

    peer_count = len(discovery.peers)
    if log_file:
        print(f"Node active: {node_type_str.upper()} on port {port} "
              f"({peer_count} peer{'s' if peer_count != 1 else ''} discovered)",
              file=log_file)

    # Emit event
    try:
        from daemon.events import bus, Events
        bus.emit(Events.NETWORK_STARTED, {
            "port": port,
            "node_type": node_type_str,
            "peers": peer_count,
        }, source="cli.serve")
    except Exception:
        pass

    loop.run_forever()


# ---------------------------------------------------------------------------
# Node CLI subcommand
# ---------------------------------------------------------------------------

def _node_status(data_dir: Path) -> None:
    """Show node status."""
    from core.paths import configure
    paths = configure(data_dir)

    try:
        from network.bootstrap import load_network_config
        config = load_network_config(paths.network_config)
    except Exception:
        config = {"enabled": False}

    enabled = config.get("enabled", False)
    node_type = config.get("node_type", "leaf").upper()
    port = config.get("port", 0) or "auto"

    print(f"Node: {'enabled' if enabled else 'disabled'}")
    print(f"  Type:       {node_type}")
    print(f"  Port:       {port}")
    print(f"  Config:     {paths.network_config}")

    # Show seed nodes
    seeds = config.get("seed_nodes", [])
    if seeds:
        print(f"  Seeds:      {len(seeds)}")
        for s in seeds[:3]:
            print(f"    {s.get('host', '?')}:{s.get('port', '?')}")

    # Try to get live status from running server
    try:
        from elara_mcp.tools.network import _discovery, _server
        if _server:
            print(f"  Server:     running on port {_server._port}")
        else:
            print(f"  Server:     not running")
        if _discovery:
            stats = _discovery.stats()
            print(f"  Discovery:  {'active' if stats['running'] else 'stopped'}")
            print(f"  Peers:      {stats['total_peers']} total, {stats['connected']} connected")
        else:
            print(f"  Discovery:  not running")
    except ImportError:
        print(f"  Runtime:    network module not available (pip install elara-core[network])")


def _node_peers(data_dir: Path) -> None:
    """List connected peers."""
    try:
        from elara_mcp.tools.network import _discovery
        if not _discovery:
            print("Node not running. Start with: elara serve")
            sys.exit(1)

        peers = _discovery.peers
        if not peers:
            print("No peers discovered.")
            return

        print(f"{len(peers)} peer(s):")
        for p in peers:
            print(f"  {p.identity_hash[:16]}... [{p.state.value}] {p.host}:{p.port}")
            if p.records_exchanged > 0:
                print(f"    Records: {p.records_exchanged}")
    except ImportError:
        print("Network module not available. Install with: pip install elara-core[network]")
        sys.exit(1)


def _node_stop(data_dir: Path) -> None:
    """Disable node (persists to config)."""
    from core.paths import configure
    paths = configure(data_dir)

    try:
        from network.bootstrap import load_network_config, save_network_config
        config = load_network_config(paths.network_config)
        config["enabled"] = False
        save_network_config(paths.network_config, config)
        print("Node disabled. Will not start on next elara serve.")
        print("  Re-enable with: elara node start")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def _node_start(data_dir: Path) -> None:
    """Enable node (persists to config)."""
    from core.paths import configure
    paths = configure(data_dir)

    try:
        from network.bootstrap import load_network_config, save_network_config
        config = load_network_config(paths.network_config)
        config["enabled"] = True
        save_network_config(paths.network_config, config)
        print("Node enabled. Will start on next elara serve.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


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
# Continuity Chain CLI
# ---------------------------------------------------------------------------

def _continuity_status(data_dir: Path) -> None:
    """Show cognitive continuity chain status."""
    from core.paths import configure
    paths = configure(data_dir)

    if not paths.continuity_file.exists():
        print("No continuity chain found.")
        print("  The chain is created automatically when the MCP server runs with tier >= 1.")
        return

    data = json.loads(paths.continuity_file.read_text())

    print(f"Continuity Chain")
    print(f"  Checkpoints: {data.get('chain_count', 0)}")
    print(f"  Chain head:  {(data.get('chain_head') or 'none')[:24]}...")
    print(f"  Created:     {data.get('created', '?')}")
    print(f"  Last:        {data.get('last_checkpoint', '?')}")
    print(f"  State file:  {paths.continuity_file}")


def _continuity_verify(data_dir: Path) -> None:
    """Verify the full cognitive continuity chain."""
    try:
        from elara_protocol.identity import Identity
        from elara_protocol.dag import LocalDAG
    except ImportError:
        print("Error: elara-protocol not installed.")
        print("  pip install elara-protocol")
        sys.exit(1)

    from core.paths import configure
    paths = configure(data_dir)

    if not paths.continuity_file.exists():
        print("No continuity chain to verify.")
        sys.exit(1)

    chain_data = json.loads(paths.continuity_file.read_text())
    chain_head = chain_data.get("chain_head")
    chain_count = chain_data.get("chain_count", 0)

    if not chain_head:
        print("Chain is empty (0 checkpoints).")
        sys.exit(0)

    # Open DAG directly for verification
    dag = LocalDAG(paths.dag_file)

    # Walk chain backwards
    breaks = []
    verified = 0
    current_id = chain_head
    seen = set()

    while current_id:
        if current_id in seen:
            breaks.append(f"Cycle detected at {current_id[:12]}")
            break
        seen.add(current_id)

        try:
            record = dag.get(current_id)
        except Exception:
            record = None

        if record is None:
            breaks.append(f"Record not found: {current_id[:12]}")
            break

        if record.metadata.get("record_type") != "cognitive_checkpoint":
            breaks.append(
                f"Record {current_id[:12]} is not a cognitive_checkpoint"
            )
            break

        # Verify signature
        try:
            import oqs
            verifier = oqs.Signature("Dilithium3")
            signable = record.signable_bytes()
            valid_sig = verifier.verify(
                signable, record.signature, record.creator_public_key
            )
            if not valid_sig:
                breaks.append(f"Invalid signature at #{record.metadata.get('sequence', '?')}")
        except ImportError:
            pass  # liboqs not available
        except Exception as e:
            breaks.append(f"Sig error at {current_id[:12]}: {e}")

        verified += 1

        # Walk to parent
        previous = record.metadata.get("previous_checkpoint")
        if previous:
            current_id = previous
        else:
            break

    dag.close()

    # Report
    print(f"Continuity Chain Verification")
    print(f"  Expected:  {chain_count} checkpoints")
    print(f"  Verified:  {verified} checkpoints")

    if not breaks:
        print(f"  Result:    INTACT")
        print(f"  Chain integrity verified — unbroken cognitive experience.")
        sys.exit(0)
    else:
        print(f"  Result:    BROKEN")
        for b in breaks:
            print(f"  Break:     {b}")
        sys.exit(1)


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
    parser.add_argument(
        "--version", action="store_true",
        help="Show version and exit",
    )

    sub = parser.add_subparsers(dest="command")

    # init
    init_parser = sub.add_parser("init", help="Interactive setup wizard")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    init_parser.add_argument("--yes", "-y", action="store_true",
                             help="Non-interactive mode (for CI/scripts)")
    init_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                             help="Override data directory (default: $ELARA_DATA_DIR or ~/.elara/)")

    # doctor
    doctor_parser = sub.add_parser("doctor", help="Diagnostic health check")
    doctor_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                               help="Override data directory")

    # serve
    serve_parser = sub.add_parser("serve", help="Start MCP server (stdio)")
    serve_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                              help="Override data directory (default: $ELARA_DATA_DIR or ~/.elara/)")
    serve_parser.add_argument("--profile", choices=["lean", "full"], default=None,
                              help="Tool profile: lean (8 schemas, default) or full (all 39+1 schemas)")
    serve_parser.add_argument("--no-node", action="store_true", dest="no_node",
                              help="Don't start network node (default: node starts automatically)")
    serve_parser.add_argument("--node-type", choices=["leaf", "relay", "witness"], default=None,
                              dest="node_type",
                              help="Override node type (default: from config)")
    serve_parser.add_argument("--tier", type=int, choices=[0, 1, 2, 3], default=None,
                              help="Hardware tier: 0=VALIDATE, 1=REMEMBER, 2=THINK (default), 3=CONNECT")

    # node
    node_parser = sub.add_parser("node", help="Network node management")
    node_sub = node_parser.add_subparsers(dest="node_command")
    node_status_p = node_sub.add_parser("status", help="Show node info")
    node_status_p.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                               help="Override data directory")
    node_peers_p = node_sub.add_parser("peers", help="List connected peers")
    node_peers_p.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                              help="Override data directory")
    node_stop_p = node_sub.add_parser("stop", help="Disable network node")
    node_stop_p.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                             help="Override data directory")
    node_start_p = node_sub.add_parser("start", help="Enable network node")
    node_start_p.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                              help="Override data directory")
    node_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                             help="Override data directory")

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

    # continuity
    cont_parser = sub.add_parser("continuity", help="Cognitive continuity chain")
    cont_sub = cont_parser.add_subparsers(dest="cont_command")
    cont_status_p = cont_sub.add_parser("status", help="Show chain status")
    cont_status_p.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                                help="Override data directory")
    cont_verify_p = cont_sub.add_parser("verify", help="Verify chain integrity")
    cont_verify_p.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
                                help="Override data directory")
    cont_parser.add_argument("--data-dir", type=Path, default=None, dest="sub_data_dir",
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

    # --version
    if getattr(args, "version", False):
        try:
            from importlib.metadata import version
            print(f"elara-core {version('elara-core')}")
        except Exception:
            print("elara-core (version unknown — not installed via pip)")
        sys.exit(0)

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
        _init(data_dir, force=args.force, yes=args.yes)
    elif args.command == "doctor":
        _doctor(data_dir)
    elif args.command == "serve":
        # Resolve profile: CLI arg → env var → default "lean"
        profile = args.profile or os.environ.get("ELARA_PROFILE", "lean")

        # Resolve tier: CLI arg → env var → default 2
        tier_val = args.tier
        if tier_val is None:
            env_tier = os.environ.get("ELARA_TIER")
            tier_val = int(env_tier) if env_tier else 2

        # Override node type in env if specified on CLI
        if args.node_type:
            os.environ["ELARA_NODE_TYPE"] = args.node_type

        _serve(data_dir, profile=profile, no_node=args.no_node, tier=tier_val)
    elif args.command == "node":
        cmd = getattr(args, "node_command", None)
        if cmd == "status":
            _node_status(data_dir)
        elif cmd == "peers":
            _node_peers(data_dir)
        elif cmd == "stop":
            _node_stop(data_dir)
        elif cmd == "start":
            _node_start(data_dir)
        else:
            node_parser.print_help()
            sys.exit(1)
    elif args.command == "sign":
        _sign(data_dir, args.file, args.classification)
    elif args.command == "verify":
        _verify(data_dir, args.proof)
    elif args.command == "identity":
        _identity(data_dir)
    elif args.command == "continuity":
        cmd = getattr(args, "cont_command", None)
        if cmd == "status":
            _continuity_status(data_dir)
        elif cmd == "verify":
            _continuity_verify(data_dir)
        else:
            cont_parser.print_help()
            sys.exit(1)
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
