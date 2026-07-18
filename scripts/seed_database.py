from __future__ import annotations

import asyncio

from backend.app.database import AsyncSessionLocal
from backend.app.runtime import configure_event_loop_policy
from backend.app.services.reference_data_service import ReferenceDataService


async def seed_data() -> None:
    async with AsyncSessionLocal() as session:
        await ReferenceDataService.ensure_seeded(session)
        await session.commit()
    print("[SUCCESS] Reference venue and routes seeded successfully.")


if __name__ == "__main__":
    configure_event_loop_policy()
    asyncio.run(seed_data())
