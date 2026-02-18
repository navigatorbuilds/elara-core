# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Integration tests — 2-node Layer 2 record exchange and witnessing."""

import asyncio

import pytest

# Skip entire module if elara_protocol not installed
pytest.importorskip("elara_protocol")

from elara_protocol.identity import Identity, EntityType, CryptoProfile
from elara_protocol.record import ValidationRecord, Classification
from elara_protocol.dag import LocalDAG

from network.server import NetworkServer
from network.client import NetworkClient
from network.trust import TrustScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def node_a(tmp_path):
    """Node A: identity + DAG + server on port 19473."""
    identity = Identity.generate(EntityType.AI, CryptoProfile.PROFILE_A)
    (tmp_path / "a").mkdir()
    dag = LocalDAG(tmp_path / "a" / "dag.sqlite")
    server = NetworkServer(identity, dag, port=19473)
    yield {"identity": identity, "dag": dag, "server": server, "port": 19473}
    dag.close()


@pytest.fixture
def node_b(tmp_path):
    """Node B: identity + DAG + server on port 19474."""
    identity = Identity.generate(EntityType.AI, CryptoProfile.PROFILE_A)
    (tmp_path / "b").mkdir()
    dag = LocalDAG(tmp_path / "b" / "dag.sqlite")
    server = NetworkServer(identity, dag, port=19474)
    yield {"identity": identity, "dag": dag, "server": server, "port": 19474}
    dag.close()


def _create_signed_record(identity, dag, content=b"test-record"):
    """Helper: create, sign, and insert a record."""
    tips = dag.tips()
    parents = [tips[-1]] if tips else []

    record = ValidationRecord.create(
        content=content,
        creator_public_key=identity.public_key,
        parents=parents,
        classification=Classification.PUBLIC,
        metadata={"source": "test"},
    )
    signable = record.signable_bytes()
    record.signature = identity.sign(signable)
    if identity.profile == CryptoProfile.PROFILE_A:
        record.sphincs_signature = identity.sign_sphincs(signable)

    dag.insert(record, verify_signature=True)
    return record


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTwoNodeExchange:
    """End-to-end tests for 2-node record exchange."""

    @pytest.mark.asyncio
    async def test_node_status_endpoint(self, node_a):
        """GET /status returns correct identity and DAG info."""
        await node_a["server"].start()
        try:
            client = NetworkClient(timeout=5.0)
            status = await client.get_status("127.0.0.1", node_a["port"])
            await client.close()

            assert status["identity"] == node_a["identity"].identity_hash
            assert status["entity_type"] == "AI"
            assert status["dag_records"] == 0
            assert status["port"] == node_a["port"]
        finally:
            await node_a["server"].stop()

    @pytest.mark.asyncio
    async def test_nodes_exchange_record(self, node_a, node_b):
        """Full flow: Node A creates record, Node B syncs it."""
        await node_a["server"].start()
        await node_b["server"].start()
        try:
            # Node A creates a record
            record = _create_signed_record(
                node_a["identity"], node_a["dag"], b"exchange-test"
            )
            assert node_a["dag"].stats()["total_records"] == 1

            client = NetworkClient(timeout=5.0)

            # Node B queries records from Node A
            remote = await client.query_records("127.0.0.1", node_a["port"])
            assert len(remote) == 1
            assert remote[0]["record_id"] == record.id

            # Node B inserts the synced record
            wire = bytes.fromhex(remote[0]["wire_hex"])
            synced = ValidationRecord.from_bytes(wire)
            node_b["dag"].insert(synced, verify_signature=False)

            assert node_b["dag"].stats()["total_records"] == 1

            # Verify it's the same record
            retrieved = node_b["dag"].get(record.id)
            assert retrieved is not None
            assert retrieved.id == record.id

            await client.close()
        finally:
            await node_a["server"].stop()
            await node_b["server"].stop()

    @pytest.mark.asyncio
    async def test_nodes_witness_record(self, node_a, node_b):
        """Full flow: Node A creates record, Node B witnesses it, trust goes up."""
        await node_a["server"].start()
        await node_b["server"].start()
        try:
            # Node A creates a record
            record = _create_signed_record(
                node_a["identity"], node_a["dag"], b"witness-test"
            )

            client = NetworkClient(timeout=5.0)

            # Node B requests witness from Node A
            wire = record.to_bytes()
            result = await client.request_witness("127.0.0.1", node_a["port"], wire)

            assert "error" not in result
            assert result["witness"] == node_a["identity"].identity_hash
            assert result["record_id"] == record.id

            # Verify attestation stored on Node A's server
            wm = node_a["server"]._witness_manager
            assert wm.witness_count(record.id) == 1

            attestations = wm.get_attestations(record.id)
            assert len(attestations) == 1
            assert attestations[0].witness_identity_hash == node_a["identity"].identity_hash

            # Verify trust score
            score = TrustScore.compute(wm.witness_count(record.id))
            assert abs(score - 0.5) < 0.01
            assert TrustScore.level(score) == "moderate"

            await client.close()
        finally:
            await node_a["server"].stop()
            await node_b["server"].stop()

    @pytest.mark.asyncio
    async def test_submit_record_to_remote(self, node_a, node_b):
        """Node A pushes a record directly to Node B via POST /records."""
        await node_b["server"].start()
        try:
            # Node A creates a record
            record = _create_signed_record(
                node_a["identity"], node_a["dag"], b"push-test"
            )

            client = NetworkClient(timeout=5.0)

            # Push to Node B
            wire = record.to_bytes()
            result = await client.submit_record("127.0.0.1", node_b["port"], wire)

            assert result.get("accepted") is True
            assert result["record_id"] == record.id

            # Verify Node B has the record
            assert node_b["dag"].stats()["total_records"] == 1
            retrieved = node_b["dag"].get(record.id)
            assert retrieved is not None

            await client.close()
        finally:
            await node_b["server"].stop()
