from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.config import settings
from backend.app.domain.gir import DirectiveAction
from backend.app.domain.guidance import GuidanceChannel, Language
from backend.app.services.reference_data_service import ReferenceDataService
from backend.app.services.venue_service import VenueService

router = APIRouter(prefix="/api/capabilities", tags=["Capabilities"])


@router.get("")
async def get_capabilities() -> dict[str, Any]:
    """Return versioned capabilities without duplicating scenario truth."""

    scenarios = VenueService.load_scenarios()
    return {
        "supported_languages": [item.value for item in Language],
        "generated_channels": [item.value for item in GuidanceChannel],
        "publication_surfaces": [
            "FAN_APP",
            "PA",
            "SIGNAGE",
            "VOLUNTEER_DEVICE",
        ],
        "scenarios": [
            {
                "key": item["key"],
                "name": item["name"],
                "description": item["description"],
            }
            for item in scenarios
        ],
        "controlled_actions": [item.value for item in DirectiveAction],
        "gemini": {
            "model": settings.GEMINI_MODEL,
            "configured": settings.gemini_configured,
            "server_side_only": True,
        },
        "demo_fault_injection_enabled": settings.ENABLE_DEMO_FAULT_INJECTION,
        "reference_data": {
            "version": VenueService.load_topology().reference_version,
            "sha256": ReferenceDataService.deployed_reference_hash(),
            "required_files": list(ReferenceDataService.REQUIRED_FILES),
        },
        "synthetic_prototype": True,
    }
