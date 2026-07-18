from typing import Any, Dict

from pydantic import BaseModel


class ScenarioTrigger(BaseModel):
    trigger_type: str  # gate_pressure, arrival_surge, asset_outage
    target_key: str
    metric_value: Any


class Scenario(BaseModel):
    key: str
    name: str
    description: str
    triggers: Dict[str, Any]


# Pinned scenarios
SCENARIOS = [
    Scenario(
        key="gate_convergence",
        name="Gate C Convergence Scenario",
        description="Gate C queues are projected to overflow, threatening corridor flow constraints.",
        triggers={
            "gate_pressure": {"gate_stable_key": "node-gate-c", "utilization_pct": 98.0}
        },
    ),
    Scenario(
        key="transit_burst",
        name="Transit Arrival Burst Scenario",
        description="Transit Hub arrival rate rises due to a delayed high-frequency transit train, causing surge flows.",
        triggers={
            "arrival_surge": {
                "arrival_node_key": "node-arrival-transit",
                "rate_multiplier": 2.5,
            }
        },
    ),
    Scenario(
        key="lift_outage",
        name="Lift D2 Breakdown Scenario",
        description="Access lift asset-lift-d2 fails. Mobility-assistance guests require alternate pathways.",
        triggers={
            "asset_outage": {"asset_stable_key": "asset-lift-d2", "status": "OFFLINE"}
        },
    ),
]
