from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def response_json(response: httpx.Response, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        raise VerificationError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}, expected {expected}: {response.text[:1000]}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise VerificationError("Expected a JSON object response.")
    return payload


def run_verification(base_url: str) -> dict[str, Any]:
    session_id = uuid4()
    headers = {"X-Session-ID": str(session_id)}
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0) as client:
        create = response_json(
            client.post(
                "/api/runs",
                json={
                    "session_id": str(session_id),
                    "scenario_key": "gate_convergence",
                },
            ),
            201,
        )
        run_id = UUID(str(create["run_id"]))
        candidate = next(
            item
            for item in create["candidates"]
            if item["candidate_key"] == "cand-west-gate-a"
        )
        require(candidate["is_viable"] is True, "Target candidate is not viable.")

        selected = response_json(
            client.post(
                f"/api/runs/{run_id}/select-candidate",
                headers=headers,
                json={"candidate_id": candidate["id"]},
            ),
            200,
        )
        require(
            selected["lifecycle_state"] == "CANDIDATE_SELECTED",
            "Candidate selection did not advance state.",
        )

        generated = response_json(
            client.post(
                f"/api/runs/{run_id}/generate-guidance",
                headers=headers,
                json={"enable_fault_injection": True},
            ),
            200,
        )
        require(
            generated["lifecycle_state"] == "PREFLIGHT_BLOCKED",
            "Fault-injected guidance was not blocked.",
        )
        require(len(generated["variants"]) == 6, "Expected six guidance variants.")
        diagnostic_codes = {item["code"] for item in generated["diagnostics"]}
        require(
            "PROTECTED_COHORT_OMITTED" in diagnostic_codes,
            "Protected cohort omission was not detected.",
        )

        blocked_approval = client.post(
            f"/api/runs/{run_id}/approve",
            headers=headers,
            json={
                "approved_by_user_id": str(uuid4()),
                "approver_role": "SUPERVISOR",
                "approval_note": "Must remain blocked.",
                "expected_bundle_hash": "0" * 64,
            },
        )
        require(
            blocked_approval.status_code == 409,
            "Approval was not blocked while semantic diagnostics were active.",
        )

        repaired = response_json(
            client.post(f"/api/runs/{run_id}/repair", headers=headers), 200
        )
        require(
            repaired["lifecycle_state"] == "SEMANTIC_PASSED",
            "Targeted repair did not restore semantic equivalence.",
        )
        require(
            repaired["repaired_variant"]["version"] == 2,
            "Targeted repair did not create an immutable second version.",
        )
        require(
            len(repaired["unaffected_variant_hashes"]) == 5,
            "The five unaffected variants were not preserved.",
        )
        require(
            repaired["unaffected_spanish_clauses_unchanged"] is True,
            "Targeted repair changed an unrelated Spanish clause.",
        )

        simulated = response_json(
            client.post(f"/api/runs/{run_id}/simulate", headers=headers), 200
        )
        simulation = simulated["simulation"]
        require(simulation["sample_count"] == 200, "Expected 200 paired samples.")
        require(simulation["paired"] is True, "Simulation is not paired.")
        require(simulation["verdict"] == "PASS", "Golden Flow simulation did not pass.")
        require(
            simulation["protected_route_violations"] == 0,
            "Protected route invariant was violated.",
        )

        details_before_approval = response_json(
            client.get(f"/api/runs/{run_id}", headers=headers), 200
        )
        bundle_hash = details_before_approval["expected_bundle_hash"]
        require(
            isinstance(bundle_hash, str) and len(bundle_hash) == 64,
            "Server bundle hash is unavailable.",
        )

        stale_approval = client.post(
            f"/api/runs/{run_id}/approve",
            headers=headers,
            json={
                "approved_by_user_id": str(uuid4()),
                "approver_role": "SUPERVISOR",
                "approval_note": "Stale hash check.",
                "expected_bundle_hash": "f" * 64,
            },
        )
        require(stale_approval.status_code == 409, "Stale bundle hash was accepted.")

        approval = response_json(
            client.post(
                f"/api/runs/{run_id}/approve",
                headers=headers,
                json={
                    "approved_by_user_id": str(uuid4()),
                    "approver_role": "SUPERVISOR",
                    "approval_note": "Synthetic Golden Flow evidence reviewed.",
                    "expected_bundle_hash": bundle_hash,
                },
            ),
            201,
        )
        require(approval["lifecycle_state"] == "APPROVED", "Approval failed.")

        published = response_json(
            client.post(f"/api/runs/{run_id}/publish", headers=headers), 202
        )
        require(published["lifecycle_state"] == "PUBLISHED", "Publish failed.")
        require(published["simulated"] is True, "Publication must be simulated.")
        require(len(published["deliveries"]) == 10, "Expected ten delivery records.")

        final_details = response_json(
            client.get(f"/api/runs/{run_id}", headers=headers), 200
        )
        require(
            len(final_details["publication_deliveries"]) == 10,
            "Publication delivery evidence was not persisted.",
        )
        require(
            final_details["approval"]["bundle_hash"] == bundle_hash,
            "Persisted approval bundle hash differs from the approved hash.",
        )

        audit = response_json(
            client.get(f"/api/runs/{run_id}/audit", headers=headers), 200
        )
        require(audit["chain_valid"] is True, "Audit hash chain is invalid.")
        event_types = [item["event_type"] for item in audit["events"]]
        for event_type in (
            "DEMO_FAULT_INJECTED",
            "SEMANTIC_BLOCKED",
            "TARGETED_REPAIR_COMPLETED",
            "SIMULATION_COMPLETED",
            "APPROVAL_RECORDED",
            "PUBLICATION_COMPLETED",
        ):
            require(event_type in event_types, f"Missing audit event {event_type}.")

        return {
            "verified": True,
            "base_url": base_url,
            "run_id": str(run_id),
            "session_id": str(session_id),
            "selected_candidate": candidate["candidate_key"],
            "generation_provenance": final_details["generation_provenance"],
            "blocked_diagnostic_codes": sorted(diagnostic_codes),
            "targeted_repair": {
                "repaired_language": repaired["repaired_variant"]["language"],
                "repaired_channel": repaired["repaired_variant"]["channel"],
                "new_version": repaired["repaired_variant"]["version"],
                "other_variant_hash_count": len(repaired["unaffected_variant_hashes"]),
                "unaffected_spanish_clauses_unchanged": repaired[
                    "unaffected_spanish_clauses_unchanged"
                ],
            },
            "simulation": simulation,
            "approval_bundle_hash": bundle_hash,
            "publication_delivery_count": len(final_details["publication_deliveries"]),
            "publication_surfaces": sorted(
                {item["surface"] for item in final_details["publication_deliveries"]}
            ),
            "audit_chain_valid": audit["chain_valid"],
            "audit_event_types": event_types,
            "final_state": final_details["lifecycle_state"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify CrowdCue Golden Flow over HTTP"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    result = run_verification(arguments.base_url)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
