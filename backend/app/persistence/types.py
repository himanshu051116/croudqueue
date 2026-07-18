from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# PostgreSQL uses JSONB for indexed/queryable operational evidence. The generic
# JSON fallback exists only so the explicit test-only SQLite harness can exercise
# service behavior without becoming a supported runtime database.
JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")
