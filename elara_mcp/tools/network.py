# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Network tool — Layer 2 peer discovery, record exchange, and witnessing.

Cortical Layer 4 — SOCIAL: Network operations. With the cortical model,
the tool handler runs in a thread pool (Layer 2 async wrapper), so
asyncio.run() works cleanly without event loop conflicts.

1 tool: elara_network(action)
"""

from typing import Optional
from elara_mcp._app import tool


@tool()
def elara_network(
    action: str = "status",
    host: Optional[str] = None,
    port: Optional[int] = None,
    record_id: Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    Layer 2 network operations — peer discovery, record exchange, witnessing.

    Requires optional dependency: pip install elara-core[network]

    Args:
        action: What to do:
            "status"       — Network status: running, peers, server port
            "peers"        — List discovered peers
            "start"        — Start network (discovery + server)
            "stop"         — Stop network
            "push"         — Push recent records to a peer (needs host, port)
            "sync"         — Pull records from a peer (needs host, port)
            "witness"      — Request witness from a peer for a record (needs host, port, record_id)
            "attestations" — Query attestations for a record from a peer (needs host, port, record_id)
        host: Peer hostname/IP (for push, sync, witness, attestations)
        port: Peer port (for push, sync, witness, attestations)
        record_id: Record ID (for witness, attestations)
        limit: Max records for sync (default 20)

    Returns:
        Network status, peer list, or operation result
    """
    if action == "status":
        return _status()
    if action == "peers":
        return _peers()
    if action == "start":
        return _start()
    if action == "stop":
        return _stop()
    if action == "push":
        if not host or not port:
            return "Error: host and port required for push."
        return _push(host, port, limit)
    if action == "sync":
        if not host or not port:
            return "Error: host and port required for sync."
        return _sync(host, port, limit)
    if action == "witness":
        if not host or not port or not record_id:
            return "Error: host, port, and record_id required for witness."
        return _witness(host, port, record_id)
    if action == "attestations":
        if not host or not port or not record_id:
            return "Error: host, port, and record_id required for attestations."
        return _attestations(host, port, record_id)
    return f"Unknown action: {action}. Use: status, peers, start, stop, push, sync, witness, attestations"


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_discovery = None
_server = None
_server_loop = None  # Event loop for the network server thread


def _get_bridge():
    """Get Layer 1 bridge (needed for identity and DAG)."""
    from core.layer1_bridge import get_bridge
    bridge = get_bridge()
    if bridge is None:
        return None
    return bridge


def _status() -> str:
    """Network status."""
    bridge = _get_bridge()
    if bridge is None:
        return "Network unavailable — Layer 1 bridge not initialized."

    lines = ["Network status:"]

    if _discovery:
        stats = _discovery.stats()
        lines.append(f"  Discovery: {'running' if stats['running'] else 'stopped'}")
        lines.append(f"  mDNS: {'active' if stats['mdns'] else 'disabled'}")
        lines.append(f"  Peers: {stats['total_peers']} ({stats['connected']} connected, {stats['stale']} stale)")
    else:
        lines.append("  Discovery: not started")

    if _server:
        lines.append(f"  Server: running on port {_server._port}")
    else:
        lines.append("  Server: not started")

    return "\n".join(lines)


def _peers() -> str:
    """List peers."""
    if not _discovery:
        return "Discovery not started. Use action='start' first."

    peers = _discovery.peers
    if not peers:
        return "No peers discovered."

    lines = [f"{len(peers)} peer(s):"]
    for p in peers:
        lines.append(f"  {p.identity_hash[:16]}... [{p.state.value}] {p.host}:{p.port}")
        if p.records_exchanged > 0:
            lines.append(f"    Records exchanged: {p.records_exchanged}")
    return "\n".join(lines)


def _start() -> str:
    """Start discovery and server."""
    global _discovery, _server, _server_loop
    bridge = _get_bridge()
    if bridge is None:
        return "Cannot start — Layer 1 bridge not initialized."

    import os
    import asyncio
    import threading
    from core.paths import get_paths
    from daemon.events import bus, Events

    paths = get_paths()
    net_port = int(os.environ.get("ELARA_NETWORK_PORT", "9473"))
    node_type_str = os.environ.get("ELARA_NODE_TYPE", "leaf")

    # Start discovery
    from network.discovery import PeerDiscovery
    from network.types import NodeType
    try:
        node_type = NodeType(node_type_str)
    except ValueError:
        node_type = NodeType.LEAF

    _discovery = PeerDiscovery(
        identity_hash=bridge._identity.identity_hash,
        port=net_port,
        peers_file=paths.network_peers,
        node_type=node_type,
    )
    _discovery.start()

    # Start HTTP server in a background thread with its own event loop
    from network.server import NetworkServer

    _paths = get_paths()
    _server = NetworkServer(
        bridge._identity, bridge._dag, port=net_port,
        attestations_db=_paths.attestations_db,
        node_type=node_type_str,
    )

    def _run_server():
        global _server_loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _server_loop = loop
        loop.run_until_complete(_server.start())
        loop.run_forever()

    thread = threading.Thread(target=_run_server, daemon=True, name="elara-network")
    thread.start()

    # Emit network start event
    bus.emit(Events.NETWORK_STARTED, {
        "port": net_port,
        "node_type": node_type_str,
    }, source="network")

    return f"Network started — discovery + server on port {net_port}"


def _stop() -> str:
    """Stop network."""
    global _discovery, _server, _server_loop
    from daemon.events import bus, Events

    if _discovery:
        _discovery.stop()
        _discovery = None

    if _server and _server_loop:
        import asyncio
        try:
            asyncio.run_coroutine_threadsafe(_server.stop(), _server_loop).result(timeout=5)
        except Exception:
            pass
        try:
            _server_loop.call_soon_threadsafe(_server_loop.stop)
        except Exception:
            pass
        _server = None
        _server_loop = None

    bus.emit(Events.NETWORK_STOPPED, {}, source="network")
    return "Network stopped."


def _run_async(coro):
    """Run an async coroutine from sync context (tool runs in thread pool)."""
    import asyncio
    return asyncio.run(coro)


def _push(host: str, port: int, limit: int) -> str:
    """Push recent records to a peer."""
    bridge = _get_bridge()
    if bridge is None:
        return "Cannot push — Layer 1 bridge not initialized."

    from network.client import NetworkClient

    async def _do_push():
        records = bridge._dag.query(limit=limit)
        if not records:
            return "No records to push."

        client = NetworkClient()
        pushed = 0
        errors = 0
        for record in records:
            wire = record.to_bytes()
            result = await client.submit_record(host, port, wire)
            if result.get("accepted"):
                pushed += 1
            else:
                errors += 1
        await client.close()
        return f"Pushed {pushed} records to {host}:{port} ({errors} errors)"

    try:
        return _run_async(_do_push())
    except Exception as e:
        return f"Push failed: {e}"


def _sync(host: str, port: int, limit: int) -> str:
    """Pull records from a peer."""
    bridge = _get_bridge()
    if bridge is None:
        return "Cannot sync — Layer 1 bridge not initialized."

    from network.client import NetworkClient

    async def _do_sync():
        client = NetworkClient()
        records = await client.query_records(host, port, limit=limit)
        await client.close()

        if not records:
            return f"No records from {host}:{port}"

        inserted = 0
        for rec_data in records:
            wire_hex = rec_data.get("wire_hex", "")
            if wire_hex:
                try:
                    from elara_protocol.record import ValidationRecord
                    wire = bytes.fromhex(wire_hex)
                    record = ValidationRecord.from_bytes(wire)
                    bridge._dag.insert(record, verify_signature=False)
                    inserted += 1
                except Exception:
                    pass

        return f"Synced {inserted}/{len(records)} records from {host}:{port}"

    try:
        return _run_async(_do_sync())
    except Exception as e:
        return f"Sync failed: {e}"


def _attestations(host: str, port: int, record_id: str) -> str:
    """Query attestations for a record from a remote node."""
    from network.client import NetworkClient

    async def _do_query():
        client = NetworkClient()
        attestations = await client.query_attestations(host, port, record_id)
        await client.close()

        if not attestations:
            return f"No attestations for record {record_id[:12]}... on {host}:{port}"

        lines = [f"{len(attestations)} attestation(s) for {record_id[:12]}...:"]
        for a in attestations:
            witness = a.get("witness_identity_hash", "?")[:16]
            ts = a.get("timestamp", 0)
            lines.append(f"  {witness}... at {ts:.0f}")
        return "\n".join(lines)

    try:
        return _run_async(_do_query())
    except Exception as e:
        return f"Query attestations failed: {e}"


def _witness(host: str, port: int, record_id: str) -> str:
    """Request witness attestation for a record."""
    bridge = _get_bridge()
    if bridge is None:
        return "Cannot witness — Layer 1 bridge not initialized."

    # Find the record in our DAG
    records = bridge._dag.query(limit=10000)
    target = None
    for r in records:
        if r.id == record_id:
            target = r
            break

    if target is None:
        return f"Record {record_id} not found in local DAG."

    from network.client import NetworkClient
    from network.trust import TrustScore

    async def _do_witness():
        wire = target.to_bytes()
        client = NetworkClient()
        result = await client.request_witness(host, port, wire)
        await client.close()

        if result.get("error"):
            return f"Witness request failed: {result['error']}"

        witness_hash = result.get("witness", "?")
        score = TrustScore.compute(1)
        level = TrustScore.level(score)

        return (
            f"Record {record_id[:12]}... witnessed by {witness_hash[:16]}...\n"
            f"  Trust: {score:.2f} ({level})"
        )

    try:
        return _run_async(_do_witness())
    except Exception as e:
        return f"Witness failed: {e}"
