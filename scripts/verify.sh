#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python}"

mkdir -p reports

"$PYTHON_BIN" scripts/secret-scan.py
"$PYTHON_BIN" -m isort --check-only backend/app backend/tests backend/alembic scripts
"$PYTHON_BIN" -m black --check backend/app backend/tests backend/alembic scripts
"$PYTHON_BIN" -m flake8 backend/app backend/tests backend/alembic scripts
"$PYTHON_BIN" -m mypy --explicit-package-bases backend/app
"$PYTHON_BIN" -m pytest backend/tests -q \
  --cov=backend.app --cov-branch --cov-report=xml:reports/coverage.xml

"$PYTHON_BIN" -m alembic -c backend/alembic.ini heads
"$PYTHON_BIN" -m alembic -c backend/alembic.ini upgrade head --sql \
  > reports/alembic-postgresql.sql

(
  cd frontend
  npm ci
  npm run lint
  npm run typecheck
  npm run build
  npm audit --audit-level=moderate
)

echo "[PASS] Credential-free CrowdCue verification completed."
echo "Docker/PostgreSQL runtime, Playwright, and live Gemini are separate gates."
