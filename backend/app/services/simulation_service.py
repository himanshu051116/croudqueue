from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from backend.app.domain.simulation import (
    FlowMetrics,
    PairedSimulationResult,
    SimulationVerdict,
)
from backend.app.services.integrity import domain_hash

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "reference_data"


class SimulationService:
    """Transparent, configuration-driven paired aggregate-flow model.

    This is intentionally not a microscopic pedestrian-safety simulator. Each sample
    draws one shared demand/capacity condition and evaluates both baseline and
    intervention under that exact condition. Scenario profiles are versioned reference
    data so Gate C, transit-burst, and lift-outage flows cannot silently share an
    inappropriate capacity model.
    """

    @staticmethod
    @lru_cache(maxsize=1)
    def _policy() -> dict[str, Any]:
        payload = json.loads(
            (REFERENCE_DIR / "simulation_policy.json").read_text(encoding="utf-8")
        )
        required = {
            "version",
            "seed",
            "sample_count",
            "confidence_z",
            "review_upper_bound",
            "block_upper_bound",
            "profiles",
            "candidate_capacity_factors",
        }
        missing = required.difference(payload)
        if missing:
            raise ValueError(
                f"Simulation policy is missing required keys: {sorted(missing)}"
            )
        return cast(dict[str, Any], payload)

    @classmethod
    def clear_cache(cls) -> None:
        cls._policy.cache_clear()

    @classmethod
    def policy_version(cls) -> str:
        return str(cls._policy()["version"])

    @staticmethod
    def _wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
        if trials <= 0:
            return 0.0, 0.0
        p = successes / trials
        denominator = 1 + (z * z / trials)
        centre = (p + (z * z / (2 * trials))) / denominator
        margin = (
            z
            * math.sqrt((p * (1 - p) / trials) + (z * z / (4 * trials * trials)))
            / denominator
        )
        return max(0.0, centre - margin), min(1.0, centre + margin)

    @classmethod
    def run_paired_simulation(
        cls,
        scenario_key: str,
        candidate_key: str,
        route_key: str,
        cohort_id: str,
        *,
        sample_count: int | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        policy = cls._policy()
        profiles = policy["profiles"]
        if scenario_key not in profiles:
            raise ValueError(f"Unknown simulation scenario '{scenario_key}'.")
        profile = profiles[scenario_key]
        resolved_sample_count = int(
            policy["sample_count"] if sample_count is None else sample_count
        )
        resolved_seed = int(policy["seed"] if seed is None else seed)
        if resolved_sample_count < 1:
            raise ValueError("sample_count must be positive.")

        capacity_factor = float(
            policy["candidate_capacity_factors"].get(candidate_key, 1.0)
        )
        rng = random.Random(resolved_seed)
        sample_contracts: list[dict[str, float]] = []
        baseline_rows: list[dict[str, float]] = []
        intervention_rows: list[dict[str, float]] = []
        protected_violations = 0
        intervention_failures = 0

        for index in range(resolved_sample_count):
            demand = max(
                float(profile["demand_min"]),
                rng.gauss(float(profile["demand_mean"]), float(profile["demand_sd"])),
            )
            baseline_capacity = max(
                float(profile["baseline_capacity_min"]),
                rng.gauss(
                    float(profile["baseline_capacity_mean"]),
                    float(profile["baseline_capacity_sd"]),
                ),
            )
            intervention_capacity = (
                max(
                    float(profile["intervention_capacity_min"]),
                    rng.gauss(
                        float(profile["intervention_capacity_mean"]),
                        float(profile["intervention_capacity_sd"]),
                    ),
                )
                * capacity_factor
            )
            response_rate = min(
                float(profile["response_rate_max"]),
                max(
                    float(profile["response_rate_min"]),
                    rng.gauss(
                        float(profile["response_rate_mean"]),
                        float(profile["response_rate_sd"]),
                    ),
                ),
            )
            corridor_factor = min(
                float(profile["corridor_factor_max"]),
                max(
                    float(profile["corridor_factor_min"]),
                    rng.gauss(
                        float(profile["corridor_factor_mean"]),
                        float(profile["corridor_factor_sd"]),
                    ),
                ),
            )
            sample = {
                "sample": float(index + 1),
                "demand": demand,
                "baseline_capacity": baseline_capacity,
                "intervention_capacity": intervention_capacity,
                "response_rate": response_rate,
                "corridor_factor": corridor_factor,
            }
            sample_contracts.append(sample)

            completion_multiplier = float(profile["completion_capacity_multiplier"])
            overload_threshold = float(profile["queue_overload_threshold"])
            unfinished_threshold = float(profile["unfinished_failure_threshold"])
            baseline_queue = max(0.0, demand - baseline_capacity)
            baseline_unfinished = max(
                0.0, demand - baseline_capacity * completion_multiplier
            )
            baseline_clearance = float(profile["baseline_clearance_offset"]) + (
                demand / baseline_capacity
            ) * float(profile["clearance_multiplier"])
            baseline_rows.append(
                {
                    "queue": baseline_queue,
                    "unfinished": baseline_unfinished,
                    "clearance": baseline_clearance,
                    "overloaded": (1.0 if baseline_queue > overload_threshold else 0.0),
                }
            )

            diverted = demand * response_rate
            remaining = demand - diverted
            effective_intervention_capacity = intervention_capacity * corridor_factor
            queue_baseline_path = max(0.0, remaining - baseline_capacity)
            queue_intervention_path = max(
                0.0, diverted - effective_intervention_capacity
            )
            max_queue = max(queue_baseline_path, queue_intervention_path)
            unfinished = max(
                0.0, remaining - baseline_capacity * completion_multiplier
            ) + max(
                0.0,
                diverted - effective_intervention_capacity * completion_multiplier,
            )
            clearance = float(profile["intervention_clearance_offset"]) + max(
                remaining / baseline_capacity,
                diverted / effective_intervention_capacity,
            ) * float(profile["clearance_multiplier"])
            overloaded = 1.0 if max_queue > overload_threshold else 0.0
            if overloaded or unfinished > unfinished_threshold:
                intervention_failures += 1
            intervention_rows.append(
                {
                    "queue": max_queue,
                    "unfinished": unfinished,
                    "clearance": clearance,
                    "overloaded": overloaded,
                }
            )

            if (
                cohort_id == "general-cohort"
                and route_key == "route-mobility-protected"
            ):
                protected_violations += 1

        def aggregate(rows: list[dict[str, float]]) -> FlowMetrics:
            return FlowMetrics(
                maximum_queue=round(
                    sum(row["queue"] for row in rows) / resolved_sample_count, 2
                ),
                overload_frequency=round(
                    sum(row["overloaded"] for row in rows) / resolved_sample_count, 4
                ),
                unfinished_demand=round(
                    sum(row["unfinished"] for row in rows) / resolved_sample_count, 2
                ),
                clearance_time_minutes=round(
                    sum(row["clearance"] for row in rows) / resolved_sample_count, 2
                ),
            )

        baseline = aggregate(baseline_rows)
        intervention = aggregate(intervention_rows)
        failure_frequency = intervention_failures / resolved_sample_count
        lower, upper = cls._wilson(
            intervention_failures,
            resolved_sample_count,
            float(policy["confidence_z"]),
        )

        if protected_violations:
            verdict = SimulationVerdict.BLOCK
            explanation = "Protected accessibility route violations were detected."
        elif upper >= float(policy["block_upper_bound"]):
            verdict = SimulationVerdict.BLOCK
            explanation = "The upper confidence bound exceeds the blocking threshold."
        elif upper >= float(policy["review_upper_bound"]):
            verdict = SimulationVerdict.REVIEW
            explanation = "The upper confidence bound requires operator review."
        else:
            verdict = SimulationVerdict.PASS
            explanation = (
                "The intervention reduces queue pressure without protected-route "
                "violations under the synthetic paired sample set."
            )

        sample_set_id = (
            f"{scenario_key}:{candidate_key}:seed-{resolved_seed}:"
            f"n-{resolved_sample_count}:policy-{policy['version']}"
        )
        samples_hash = domain_hash("CROWDCUE_SIMULATION_SAMPLES_V1", sample_contracts)
        result_payload = {
            "policy_version": policy["version"],
            "sample_set_id": sample_set_id,
            "seed": resolved_seed,
            "sample_count": resolved_sample_count,
            "paired": True,
            "baseline": baseline,
            "intervention": intervention,
            "protected_route_violations": protected_violations,
            "failure_frequency": failure_frequency,
            "wilson_95_lower": lower,
            "wilson_95_upper": upper,
            "verdict": verdict,
            "explanation": explanation,
            "samples_hash": samples_hash,
        }
        result_hash = domain_hash("CROWDCUE_SIMULATION_RESULT_V1", result_payload)
        result = PairedSimulationResult(
            sample_set_id=sample_set_id,
            seed=resolved_seed,
            sample_count=resolved_sample_count,
            paired=True,
            baseline=baseline,
            intervention=intervention,
            protected_route_violations=protected_violations,
            failure_frequency=failure_frequency,
            wilson_95_lower=lower,
            wilson_95_upper=upper,
            verdict=verdict,
            explanation=explanation,
            samples_hash=samples_hash,
            result_hash=result_hash,
            trace_summary={
                "baseline_queue_p95": round(
                    sorted(row["queue"] for row in baseline_rows)[
                        min(
                            resolved_sample_count - 1,
                            int(resolved_sample_count * 0.95),
                        )
                    ],
                    2,
                ),
                "intervention_queue_p95": round(
                    sorted(row["queue"] for row in intervention_rows)[
                        min(
                            resolved_sample_count - 1,
                            int(resolved_sample_count * 0.95),
                        )
                    ],
                    2,
                ),
            },
        )
        return {
            "policy_version": policy["version"],
            **result.model_dump(mode="json"),
        }
