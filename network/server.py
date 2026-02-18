# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""Network server — HTTP endpoints for record exchange and witnessing."""

import json
import logging
import time
from typing import Optional

logger = logging.getLogger("elara.network.server")


class NetworkServer:
    """
    HTTP server for Layer 2 record exchange.

    Endpoints:
        POST /records     — receive record wire bytes
        GET  /records     — query recent records
        POST /witness     — request witness attestation
        GET  /status      — node identity and DAG info
    """

    def __init__(self, identity, dag, port: int = 9473):
        self._identity = identity
        self._dag = dag
        self._port = port
        self._app = None
        self._runner = None
        self._witness_manager = None

    async def start(self) -> None:
        """Start the aiohttp server."""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp not installed — network server disabled")
            return

        from network.witness import WitnessManager
        self._witness_manager = WitnessManager()

        self._app = web.Application()
        self._app.router.add_post("/records", self._handle_submit_record)
        self._app.router.add_get("/records", self._handle_query_records)
        self._app.router.add_post("/witness", self._handle_witness)
        self._app.router.add_get("/status", self._handle_status)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()

        logger.info("Network server started on port %d", self._port)

        from daemon.events import bus, Events
        bus.emit(Events.NETWORK_STARTED, {
            "port": self._port,
            "identity": self._identity.identity_hash[:16],
        }, source="network.server")

    async def stop(self) -> None:
        """Stop the server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._app = None
            logger.info("Network server stopped")

    async def _handle_submit_record(self, request) -> "web.Response":
        """POST /records — receive and validate a remote record."""
        from aiohttp import web

        try:
            body = await request.read()
            if not body:
                return web.json_response({"error": "empty body"}, status=400)

            # Decode wire bytes
            from elara_protocol.record import ValidationRecord
            record = ValidationRecord.from_bytes(body)

            # Verify signature
            signable = record.signable_bytes()
            try:
                import oqs
                verifier = oqs.Signature("Dilithium3")
                if not verifier.verify(signable, record.signature, record.creator_public_key):
                    return web.json_response({"error": "invalid signature"}, status=403)
            except ImportError:
                logger.warning("liboqs not available — accepting without signature verification")

            # Insert into DAG (skip parent check for foreign records)
            record_hash = self._dag.insert(record, verify_signature=False)

            from daemon.events import bus, Events
            bus.emit(Events.RECORD_RECEIVED, {
                "record_id": record.id,
                "record_hash": record_hash,
                "creator": record.creator_public_key[:16].hex(),
            }, source="network.server")

            return web.json_response({
                "record_id": record.id,
                "record_hash": record_hash,
                "accepted": True,
            })

        except Exception as e:
            logger.exception("Error receiving record")
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_query_records(self, request) -> "web.Response":
        """GET /records?since=<ts>&limit=<n> — return recent records."""
        from aiohttp import web

        try:
            limit = int(request.query.get("limit", "20"))
            limit = min(limit, 100)
            since = float(request.query.get("since", "0"))

            records = self._dag.query(limit=limit)

            # Filter by timestamp if requested
            if since > 0:
                records = [r for r in records if r.timestamp > since]

            result = []
            for r in records:
                result.append({
                    "record_id": r.id,
                    "wire_hex": r.to_bytes().hex(),
                    "timestamp": r.timestamp,
                })

            return web.json_response({"records": result, "count": len(result)})

        except Exception as e:
            logger.exception("Error querying records")
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_witness(self, request) -> "web.Response":
        """POST /witness — counter-sign a record with local identity."""
        from aiohttp import web

        try:
            body = await request.read()
            if not body:
                return web.json_response({"error": "empty body"}, status=400)

            from elara_protocol.record import ValidationRecord
            record = ValidationRecord.from_bytes(body)

            # Verify the record's original signature first
            signable = record.signable_bytes()
            try:
                import oqs
                verifier = oqs.Signature("Dilithium3")
                if not verifier.verify(signable, record.signature, record.creator_public_key):
                    return web.json_response({"error": "original signature invalid"}, status=403)
            except ImportError:
                pass

            # Counter-sign with our identity
            witness_sig = self._identity.sign(signable)

            from network.types import WitnessAttestation
            attestation = WitnessAttestation(
                record_id=record.id,
                witness_identity_hash=self._identity.identity_hash,
                witness_signature=witness_sig,
                timestamp=time.time(),
            )

            self._witness_manager.add_attestation(attestation)

            from daemon.events import bus, Events
            bus.emit(Events.RECORD_WITNESSED, {
                "record_id": record.id,
                "witness": self._identity.identity_hash[:16],
            }, source="network.server")

            return web.json_response({
                "record_id": record.id,
                "witness": self._identity.identity_hash,
                "signature": witness_sig.hex(),
                "timestamp": attestation.timestamp,
            })

        except Exception as e:
            logger.exception("Error witnessing record")
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_status(self, request) -> "web.Response":
        """GET /status — identity and DAG info."""
        from aiohttp import web

        stats = self._dag.stats()
        return web.json_response({
            "identity": self._identity.identity_hash,
            "entity_type": self._identity.entity_type.name,
            "dag_records": stats.get("total_records", 0),
            "port": self._port,
        })
