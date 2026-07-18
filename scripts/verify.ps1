[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$IncludeDocker,
    [switch]$IncludeE2E
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force -Path ".\reports" | Out-Null

& $Python scripts/secret-scan.py
if ($LASTEXITCODE -ne 0) { throw "Secret scan failed." }

& $Python -m isort --check-only backend/app backend/tests backend/alembic scripts
if ($LASTEXITCODE -ne 0) { throw "isort failed." }

& $Python -m black --check backend/app backend/tests backend/alembic scripts
if ($LASTEXITCODE -ne 0) { throw "Black failed." }

& $Python -m flake8 backend/app backend/tests backend/alembic scripts
if ($LASTEXITCODE -ne 0) { throw "Flake8 failed." }

& $Python -m mypy --explicit-package-bases backend/app
if ($LASTEXITCODE -ne 0) { throw "Mypy failed." }

& $Python -m pytest backend/tests -q --cov=backend.app --cov-branch --cov-report=xml:reports/coverage.xml
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

& $Python -m alembic -c backend/alembic.ini heads
if ($LASTEXITCODE -ne 0) { throw "Alembic head check failed." }

& $Python -m alembic -c backend/alembic.ini upgrade head --sql | Set-Content -Encoding UTF8 reports/alembic-postgresql.sql
if ($LASTEXITCODE -ne 0) { throw "Alembic offline SQL generation failed." }

Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw "Frontend lint failed." }
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    npm audit --audit-level=moderate
    if ($LASTEXITCODE -ne 0) { throw "npm audit failed." }
    if ($IncludeE2E) {
        npm run test:e2e
        if ($LASTEXITCODE -ne 0) { throw "Playwright E2E failed." }
    }
}
finally {
    Pop-Location
}

if ($IncludeDocker) {
    docker compose down -v
    docker compose up --build -d
    docker compose ps
    & $Python scripts/verify_golden_flow.py --base-url http://127.0.0.1:8001 --output reports/golden-flow-docker.json
    if ($LASTEXITCODE -ne 0) { throw "Docker Golden Flow verification failed." }
}

Write-Host "[PASS] CrowdCue verification completed." -ForegroundColor Green
