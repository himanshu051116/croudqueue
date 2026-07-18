"""
Domain contracts for CrowdCue 2.0.

This module is the correct home for Pydantic domain models and value objects.
SQLAlchemy persistence modules (persistence/models/) must NOT import from pydantic —
they contain only ORM mappings.

Domain contracts here may be used by:
  - API request/response schemas (app/api/)
  - Service layer (app/services/)
  - Domain logic (app/domain/)

They must NOT directly import from persistence modules.
"""

from __future__ import annotations

# Phase 2 will add: GuidanceVariant, CompiledMeaning, InterventionCandidate,
# VenueTopology, ScenarioSnapshot domain contracts here.
