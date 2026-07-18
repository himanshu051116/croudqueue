from __future__ import annotations

from enum import Enum


class LifecycleState(str, Enum):
    DRAFT = "DRAFT"
    CANDIDATE_SELECTED = "CANDIDATE_SELECTED"
    GUIDANCE_VERIFYING = "GUIDANCE_VERIFYING"
    PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
    SEMANTIC_PASSED = "SEMANTIC_PASSED"
    SIMULATION_RUNNING = "SIMULATION_RUNNING"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    APPROVED = "APPROVED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"


class DirectiveStrength(str, Enum):
    INFO = "INFO"
    RECOMMENDED = "RECOMMENDED"
    MANDATORY = "MANDATORY"


VALID_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.DRAFT: frozenset({LifecycleState.CANDIDATE_SELECTED}),
    LifecycleState.CANDIDATE_SELECTED: frozenset({LifecycleState.GUIDANCE_VERIFYING}),
    LifecycleState.GUIDANCE_VERIFYING: frozenset(
        {
            LifecycleState.CANDIDATE_SELECTED,
            LifecycleState.PREFLIGHT_BLOCKED,
            LifecycleState.SEMANTIC_PASSED,
        }
    ),
    LifecycleState.PREFLIGHT_BLOCKED: frozenset({LifecycleState.GUIDANCE_VERIFYING}),
    LifecycleState.SEMANTIC_PASSED: frozenset({LifecycleState.SIMULATION_RUNNING}),
    LifecycleState.SIMULATION_RUNNING: frozenset(
        {LifecycleState.PREFLIGHT_PASSED, LifecycleState.PREFLIGHT_BLOCKED}
    ),
    LifecycleState.PREFLIGHT_PASSED: frozenset({LifecycleState.APPROVED}),
    LifecycleState.APPROVED: frozenset({LifecycleState.PUBLISHING}),
    LifecycleState.PUBLISHING: frozenset({LifecycleState.PUBLISHED}),
    LifecycleState.PUBLISHED: frozenset(),
}


def validate_transition(current: LifecycleState, target: LifecycleState) -> bool:
    return target in VALID_TRANSITIONS.get(current, frozenset())
