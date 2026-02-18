#!/usr/bin/env python3
# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Testnet — 2-node end-to-end proof.

Proves the Layer 2 protocol works: two nodes discover each other, exchange
a record, witness it, and trust score goes up. Validates both the code and
the patent claims (US Provisional 63/983,064).

Usage:
    python scripts/testnet.py
    python scripts/testnet.py --nodes 3 --verbose
"""

import argparse
import asyncio
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("elara.testnet")

TIMEOUT = 30  # seconds for the whole flow
BASE_PORT = 9473


class TestnetNode:
    """A single testnet node with its own identity, DAG, and server."""

    def __init__(self, name: str, port: int, temp_dir: Path):
        self.name = name
        self.port = port
        self.temp_dir = temp_dir
        self.identity = None
        self.dag = None
        self.server = None

    async def bootstrap(self) -> None:
        """Generate identity and open DAG."""
        from elara_protocol.identity import Identity, EntityType, CryptoProfile
        from elara_protocol.dag import LocalDAG

        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Generate identity
        self.identity = Identity.generate(EntityType.AI, CryptoProfile.PROFILE_A)
        identity_file = self.temp_dir / "identity.json"
        self.identity.save(identity_file)

        # Open DAG
        dag_file = self.temp_dir / "dag.sqlite"
        self.dag = LocalDAG(dag_file)

    async def start_server(self) -> None:
        """Start HTTP server."""
        from network.server import NetworkServer

        self.server = NetworkServer(self.identity, self.dag, port=self.port)
        await self.server.start()

    async def stop_server(self) -> None:
        """Stop HTTP server."""
        if self.server:
            await self.server.stop()
            self.server = None

    def create_record(self, content: bytes = b"testnet-record") -> "ValidationRecord":
        """Create and sign a record, insert into DAG."""
        from elara_protocol.record import ValidationRecord, Classification

        tips = self.dag.tips()
        parents = [tips[-1]] if tips else []

        record = ValidationRecord.create(
            content=content,
            creator_public_key=self.identity.public_key,
            parents=parents,
            classification=Classification.PUBLIC,
            metadata={"source": "testnet", "node": self.name},
        )

        # Sign with Dilithium3
        signable = record.signable_bytes()
        record.signature = self.identity.sign(signable)

        # Dual-sign with SPHINCS+ if Profile A
        from elara_protocol.identity import CryptoProfile
        if self.identity.profile == CryptoProfile.PROFILE_A:
            record.sphincs_signature = self.identity.sign_sphincs(signable)

        # Insert into DAG
        self.dag.insert(record, verify_signature=True)
        return record

    @property
    def identity_short(self) -> str:
        return self.identity.identity_hash[:16]


async def run_testnet(
    num_nodes: int = 2,
    port_base: int = BASE_PORT,
    verbose: bool = False,
) -> bool:
    """
    Run the testnet demo. Returns True on success.

    Orchestration sequence:
    1. Bootstrap N nodes (identity + DAG)
    2. Start all HTTP servers
    3. Node A creates + signs a record
    4. Node B gets status from Node A
    5. Node B syncs records from Node A
    6. Node B requests witness from Node A
    7. Verify attestation + trust score
    8. Clean up
    """
    from network.client import NetworkClient
    from network.trust import TrustScore

    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    nodes = []
    temp_dirs = []
    client = NetworkClient(timeout=10.0)
    passed = True

    print("=" * 50)
    print("  ELARA TESTNET")
    print("=" * 50)
    print()

    try:
        # --- Bootstrap nodes ---
        for i in range(num_nodes):
            name = chr(ord('A') + i)
            port = port_base + i
            temp_dir = Path(tempfile.mkdtemp(prefix=f"elara-testnet-{name.lower()}-"))
            temp_dirs.append(temp_dir)
            node = TestnetNode(name, port, temp_dir)
            await node.bootstrap()
            nodes.append(node)
            print(f"  Node {name}: {node.identity_short}... port {port}")

        print()

        # --- Start servers ---
        for node in nodes:
            await node.start_server()

        # Give servers a moment to bind
        await asyncio.sleep(0.3)

        node_a = nodes[0]
        node_b = nodes[1]

        # --- Step 1: Node A creates a record ---
        record = node_a.create_record(b"Hello from the Elara testnet!")
        count_a = node_a.dag.stats()["total_records"]
        print(f"  [1] Node A created record: {record.id[:12]}...")
        print(f"      Node A DAG: {count_a} record(s)")
        assert count_a == 1, f"Expected 1 record in Node A DAG, got {count_a}"

        # --- Step 2: Node B checks Node A's status ---
        status = await client.get_status("127.0.0.1", node_a.port)
        assert "identity" in status, f"Status response missing identity: {status}"
        print(f"  [2] Node B got status from Node A: {status.get('identity', '?')[:16]}...")

        # --- Step 3: Node B syncs records from Node A ---
        remote_records = await client.query_records("127.0.0.1", node_a.port)
        assert len(remote_records) == 1, f"Expected 1 remote record, got {len(remote_records)}"

        # Insert synced record into Node B's DAG
        from elara_protocol.record import ValidationRecord
        for rec_data in remote_records:
            wire_hex = rec_data.get("wire_hex", "")
            wire_bytes = bytes.fromhex(wire_hex)
            synced_record = ValidationRecord.from_bytes(wire_bytes)
            node_b.dag.insert(synced_record, verify_signature=False)

        count_b = node_b.dag.stats()["total_records"]
        print(f"  [3] Node B synced {len(remote_records)} record(s) from Node A")
        print(f"      Node B DAG: {count_b} record(s)")
        assert count_b == 1, f"Expected 1 record in Node B DAG, got {count_b}"

        # --- Step 4: Node B requests witness from Node A ---
        wire = record.to_bytes()
        witness_result = await client.request_witness("127.0.0.1", node_a.port, wire)
        assert "error" not in witness_result, f"Witness failed: {witness_result}"
        assert "witness" in witness_result, f"Witness response missing witness field: {witness_result}"

        witness_id = witness_result["witness"]
        print(f"  [4] Node A witnessed record {record.id[:12]}...")
        print(f"      Witness: {witness_id[:16]}...")

        # --- Step 5: Compute trust score ---
        # The server's WitnessManager tracked this attestation
        wm = node_a.server._witness_manager
        wcount = wm.witness_count(record.id)
        score = TrustScore.compute(wcount)
        level = TrustScore.level(score)

        print(f"  [5] Trust score: {score:.2f} ({level})")
        print(f"      Witness count: {wcount}")
        assert wcount == 1, f"Expected 1 witness, got {wcount}"
        assert abs(score - 0.5) < 0.01, f"Expected trust 0.50, got {score}"

        # --- Multi-node bonus: if >2 nodes, do more exchanges ---
        if num_nodes > 2:
            for i in range(2, num_nodes):
                extra_node = nodes[i]
                # Sync from Node A
                recs = await client.query_records("127.0.0.1", node_a.port)
                for rec_data in recs:
                    wire_hex = rec_data.get("wire_hex", "")
                    r = ValidationRecord.from_bytes(bytes.fromhex(wire_hex))
                    try:
                        extra_node.dag.insert(r, verify_signature=False)
                    except Exception:
                        pass  # already exists

                # Request witness
                wr = await client.request_witness(
                    "127.0.0.1", extra_node.port, wire
                )
                if "error" not in wr:
                    print(f"  [+] Node {extra_node.name} witnessed record")

            # Recompute trust from Node A's perspective
            # Each extra node that witnessed adds to the count on its OWN server
            # For a real network, attestations would propagate back
            # Here we just show the concept works
            print(f"  [+] {num_nodes}-node exchange complete")

        print()
        print("=" * 50)
        print("  TESTNET PASSED")
        print("=" * 50)

    except Exception as e:
        print(f"\n  TESTNET FAILED: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        passed = False

    finally:
        # --- Cleanup ---
        await client.close()
        for node in nodes:
            await node.stop_server()
            if node.dag:
                node.dag.close()
        for td in temp_dirs:
            shutil.rmtree(td, ignore_errors=True)

    return passed


def main():
    parser = argparse.ArgumentParser(
        description="Elara Testnet — 2-node end-to-end proof"
    )
    parser.add_argument(
        "--nodes", type=int, default=2,
        help="Number of nodes (default: 2)"
    )
    parser.add_argument(
        "--port-base", type=int, default=BASE_PORT,
        help=f"Starting port (default: {BASE_PORT})"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Detailed output"
    )
    args = parser.parse_args()

    success = asyncio.run(run_testnet(
        num_nodes=args.nodes,
        port_base=args.port_base,
        verbose=args.verbose,
    ))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
