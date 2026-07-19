"""Read-model contract tests protecting API response structure and ordering invariants.

These tests ensure that refactoring the read_model.py does not change:
- API response keys or structure
- Ordering of candidates, variants, audit events, and publications
- Deterministic hash contracts
- Exception behavior
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.services.golden_flow_service import GoldenFlowService


class TestReadModelResponseStructure:
    """Verify that read-model responses contain exact expected keys."""

    @pytest.mark.asyncio
    async def test_details_response_has_exact_expected_keys(
        self, client: AsyncClient
    ) -> None:
        """Ensure details response preserves all required JSON keys."""
        session_id = uuid4()
        response = await client.post(
            "/api/runs",
            json={"session_id": str(session_id), "scenario_key": "gate_convergence"},
        )
        assert response.status_code == 201
        created = response.json()
        run_id = created["run_id"]

        # Get details through API with required header
        details_response = await client.get(
            f"/api/runs/{run_id}",
            headers={"X-Session-ID": str(session_id)},
        )
        assert details_response.status_code == 200
        details = details_response.json()

        # Verify exact set of top-level keys
        expected_top_keys = {
            "run_id",
            "session_id",
            "scenario_key",
            "lifecycle_state",
            "run_version",
            "selected_candidate_id",
            "snapshot_hash",
            "gir",
            "candidates",
            "generation_provenance",
            "variants",
            "diagnostics",
            "simulation",
            "approval",
            "publication_batch",
            "publication_deliveries",
            "expected_bundle_hash",
            "decision_bundle_hash",
        }
        assert set(details.keys()) == expected_top_keys

        # Verify candidate structure
        assert isinstance(details["candidates"], list)
        if details["candidates"]:
            candidate = details["candidates"][0]
            expected_candidate_keys = {
                "id",
                "candidate_key",
                "title",
                "cohort_id",
                "destination_id",
                "route_id",
                "is_viable",
                "preliminary_rank",
                "selected",
                "rejections",
            }
            assert set(candidate.keys()) == expected_candidate_keys

            # Verify rejection structure
            if candidate["rejections"]:
                rejection = candidate["rejections"][0]
                expected_rejection_keys = {
                    "reason_code",
                    "message",
                    "affected_route_id",
                    "affected_edge_key",
                    "affected_asset_key",
                }
                assert set(rejection.keys()) == expected_rejection_keys

        # Verify variant structure
        assert isinstance(details["variants"], list)
        if details["variants"]:
            variant = details["variants"][0]
            expected_variant_keys = {
                "id",
                "language",
                "channel",
                "version",
                "audience_action",
                "route_clause",
                "fallback_clause",
                "protection_clause",
                "validity_clause",
                "optional_explanation",
                "rendered_text",
                "content_hash",
            }
            assert set(variant.keys()) == expected_variant_keys

        # Verify publication delivery structure
        assert isinstance(details["publication_deliveries"], list)
        if details["publication_deliveries"]:
            delivery = details["publication_deliveries"][0]
            expected_delivery_keys = {
                "surface",
                "language",
                "status",
                "variant_id",
                "error_message",
                "delivered_at",
            }
            assert set(delivery.keys()) == expected_delivery_keys

    @pytest.mark.asyncio
    async def test_snapshot_details_response_has_exact_keys(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure snapshot_details returns exact expected structure."""
        from backend.app.persistence.models.run import PreflightRun as RunModel
        from backend.app.persistence.models.run import (
            VenueStateSnapshot as SnapshotModel,
        )

        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        # Get the actual snapshot ID from the database
        run = await db_session.get(RunModel, run_id)
        assert run is not None
        snapshot_id = run.venue_state_snapshot_id

        # Call snapshot_details directly
        snapshot = await GoldenFlowService.snapshot_details(
            db_session, snapshot_id=snapshot_id, session_id=session_id
        )

        expected_keys = {
            "id",
            "session_id",
            "venue_id",
            "scenario_key",
            "reference_data_version",
            "canonical_input_hash",
            "timestamp",
            "nodes_state",
            "edges_state",
            "assets_state",
        }
        assert set(snapshot.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_audit_timeline_response_has_exact_keys(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure audit_timeline returns exact expected structure."""
        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        timeline = await GoldenFlowService.audit_timeline(
            db_session, run_id=run_id, session_id=session_id
        )

        expected_top_keys = {
            "run_id",
            "chain_scope",
            "session_event_count",
            "chain_valid",
            "events",
        }
        assert set(timeline.keys()) == expected_top_keys

        # Verify event structure
        assert isinstance(timeline["events"], list)
        if timeline["events"]:
            event = timeline["events"][0]
            expected_event_keys = {
                "id",
                "sequence_number",
                "event_type",
                "payload",
                "created_at",
                "previous_event_hash",
                "event_hash",
            }
            assert set(event.keys()) == expected_event_keys


class TestReadModelOrderingInvariants:
    """Verify that read-model ordering is deterministic and preserved."""

    @pytest.mark.asyncio
    async def test_candidate_ordering_is_deterministic(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure candidates are returned in consistent order across calls."""
        session_id = uuid4()
        created1 = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created1["run_id"]

        # Get details multiple times
        details1 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )
        details2 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        # Candidates should be in same order
        ids1 = [c["id"] for c in details1["candidates"]]
        ids2 = [c["id"] for c in details2["candidates"]]
        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_variant_ordering_is_preserved_across_refactoring(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure guidance variants maintain consistent ordering."""
        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        # Select a candidate to enable guidance generation
        candidate = next(
            item
            for item in created["candidates"]
            if item["candidate_key"] == "cand-west-gate-a"
        )
        await GoldenFlowService.select_candidate(
            db_session,
            run_id=run_id,
            session_id=session_id,
            candidate_id=candidate["id"],
        )

        # Generate guidance
        generated1 = await GoldenFlowService.generate_guidance(
            db_session,
            run_id=run_id,
            session_id=session_id,
            enable_fault_injection=False,
        )

        # Get details
        details1 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        # Get details again
        details2 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        # Variants should be in same order and same hashes
        variants1 = details1["variants"]
        variants2 = details2["variants"]

        assert len(variants1) == len(variants2)
        for v1, v2 in zip(variants1, variants2):
            assert v1["id"] == v2["id"]
            assert v1["language"] == v2["language"]
            assert v1["channel"] == v2["channel"]
            assert v1["content_hash"] == v2["content_hash"]

    @pytest.mark.asyncio
    async def test_audit_timeline_ordering_is_consistent(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure audit events maintain sequence order across reads."""
        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        timeline1 = await GoldenFlowService.audit_timeline(
            db_session, run_id=run_id, session_id=session_id
        )

        timeline2 = await GoldenFlowService.audit_timeline(
            db_session, run_id=run_id, session_id=session_id
        )

        # Event order should be identical
        events1 = timeline1["events"]
        events2 = timeline2["events"]

        assert len(events1) == len(events2)
        for e1, e2 in zip(events1, events2):
            assert e1["sequence_number"] == e2["sequence_number"]
            assert e1["event_type"] == e2["event_type"]

    @pytest.mark.asyncio
    async def test_publication_delivery_ordering_is_preserved(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure publication deliveries maintain consistent sort order."""
        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        # Select candidate and generate guidance to enable publication
        candidate = next(
            item
            for item in created["candidates"]
            if item["candidate_key"] == "cand-west-gate-a"
        )
        await GoldenFlowService.select_candidate(
            db_session,
            run_id=run_id,
            session_id=session_id,
            candidate_id=candidate["id"],
        )

        await GoldenFlowService.generate_guidance(
            db_session,
            run_id=run_id,
            session_id=session_id,
            enable_fault_injection=False,
        )

        await GoldenFlowService.simulate(
            db_session, run_id=run_id, session_id=session_id
        )

        # Get expected hash before approval (returns str | None)
        expected_hash = await GoldenFlowService.expected_bundle_hash(
            db_session, run_id=run_id, session_id=session_id
        )

        assert expected_hash is not None

        # Approve with required parameters
        from uuid import uuid4 as new_uuid

        await GoldenFlowService.approve(
            db_session,
            run_id=run_id,
            session_id=session_id,
            approved_by_user_id=new_uuid(),
            approver_role="OPERATOR",
            approval_note="Test approval",
            expected_bundle_hash=expected_hash,
        )

        # Publish
        await GoldenFlowService.publish(
            db_session, run_id=run_id, session_id=session_id
        )

        # Get details twice
        details1 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        details2 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        # Publication deliveries should be in same order
        deliveries1 = details1["publication_deliveries"]
        deliveries2 = details2["publication_deliveries"]

        assert len(deliveries1) == len(deliveries2)
        for d1, d2 in zip(deliveries1, deliveries2):
            assert d1["surface"] == d2["surface"]
            assert d1["language"] == d2["language"]


class TestReadModelHashContracts:
    """Verify that read-model hash contracts remain deterministic."""

    @pytest.mark.asyncio
    async def test_candidate_rejection_structure_is_stable(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure candidate rejections serialize consistently."""
        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        details1 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        details2 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        # Rejection structures should match exactly
        for idx, candidate in enumerate(details1["candidates"]):
            rejections1 = candidate["rejections"]
            rejections2 = details2["candidates"][idx]["rejections"]

            assert len(rejections1) == len(rejections2)
            for r1, r2 in zip(rejections1, rejections2):
                assert r1["reason_code"] == r2["reason_code"]
                assert r1["message"] == r2["message"]
                assert r1["affected_route_id"] == r2["affected_route_id"]
                assert r1["affected_edge_key"] == r2["affected_edge_key"]
                assert r1["affected_asset_key"] == r2["affected_asset_key"]

    @pytest.mark.asyncio
    async def test_variant_hashes_are_deterministic_across_reads(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure variant content hashes remain stable across queries."""
        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        candidate = next(
            item
            for item in created["candidates"]
            if item["candidate_key"] == "cand-west-gate-a"
        )
        await GoldenFlowService.select_candidate(
            db_session,
            run_id=run_id,
            session_id=session_id,
            candidate_id=candidate["id"],
        )

        await GoldenFlowService.generate_guidance(
            db_session,
            run_id=run_id,
            session_id=session_id,
            enable_fault_injection=False,
        )

        details1 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        details2 = await GoldenFlowService.details(
            db_session, run_id=run_id, session_id=session_id
        )

        # All variant hashes should match
        hashes1 = {v["id"]: v["content_hash"] for v in details1["variants"]}
        hashes2 = {v["id"]: v["content_hash"] for v in details2["variants"]}

        assert hashes1 == hashes2


class TestReadModelExceptionBehavior:
    """Verify that read-model error handling remains unchanged."""

    @pytest.mark.asyncio
    async def test_missing_run_raises_run_not_found_error(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure missing run raises expected error."""
        from backend.app.services.golden_flow.common import RunNotFoundError

        session_id = uuid4()
        nonexistent_run_id = uuid4()

        with pytest.raises(RunNotFoundError):
            await GoldenFlowService.details(
                db_session, run_id=nonexistent_run_id, session_id=session_id
            )

    @pytest.mark.asyncio
    async def test_unauthorized_session_access_raises_ownership_error(
        self, db_session: AsyncSession
    ) -> None:
        """Ensure unauthorized session access raises expected error."""
        from backend.app.services.golden_flow.common import OwnershipError

        session_id = uuid4()
        created = await GoldenFlowService.create_run(
            db_session, session_id=session_id, scenario_key="gate_convergence"
        )
        run_id = created["run_id"]

        # Try to access with different session_id
        other_session_id = uuid4()

        with pytest.raises(OwnershipError):
            await GoldenFlowService.details(
                db_session, run_id=run_id, session_id=other_session_id
            )
