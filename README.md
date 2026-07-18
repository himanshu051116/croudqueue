# CrowdCue 2.0

**CrowdCue 26 · Guidance Preflight** is a full-stack, synthetic stadium-operations prototype that checks multilingual guidance before simulated publication.

> **A message can be right for one fan. And wrong for the crowd.**

CrowdCue treats generated guidance as untrusted. A structured **Guidance Intermediate Representation (GIR)** remains authoritative; rendered EN/ES/FR Fan App and PA messages are reverse-compiled, compared with the GIR, checked against accessibility and workflow invariants, stress-tested with a transparent paired aggregate-flow model, and then submitted for explicit human approval.

## Golden Flow

The implemented Gate C flow demonstrates:

1. Aurora Stadium synthetic venue and Gate C convergence state.
2. Configuration-driven intervention candidates and deterministic vetoes.
3. Operator selection of the targeted Gate A diversion.
4. Immutable GIR creation.
5. One multilingual Gemini request when configured, otherwise controlled deterministic fallback.
6. Six verified variants: EN/ES/FR for Fan App and PA.
7. Demo-only omission of the Spanish Fan App mobility-assistance clause.
8. Reverse compilation and `PROTECTED_COHORT_OMITTED` blocking diagnostic.
9. Immutable targeted repair creating Spanish Fan App version 2 while preserving all unrelated content.
10. A reproducible 200-sample paired aggregate-flow comparison.
11. Server-recomputed approval bundle hash.
12. Simulated delivery to Fan App, PA, Signage, and Volunteer Device surfaces.
13. PostgreSQL-backed, hash-chained audit evidence in the deployment architecture.

## Honesty and scope

- All venue states, response assumptions, simulation samples, and publication events are synthetic.
- CrowdCue does not connect to FIFA or a live stadium system.
- The simulator is not a certified pedestrian-safety model.
- Gemini is optional for product continuity. The UI and provenance clearly distinguish live model output from deterministic fallback.
- Demo fault injection is disabled by default and rejected in production configuration.

## Stack

- **Frontend:** React 18, TypeScript, Vite 8, Tailwind CSS, Playwright, axe-core.
- **Backend:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, psycopg 3.
- **State:** PostgreSQL 17 is authoritative; Redis 7 is transient infrastructure.
- **AI:** server-side Gemini Interactions API integration with structured output, bounded retry, safe errors, and deterministic fallback.
- **Deployment:** Docker Compose, non-root runtime containers, nginx API proxy.

## Repository layout

```text
backend/                 FastAPI, domain, persistence, services, migrations, tests
frontend/                React command-centre UI and Playwright tests
reference_data/          Versioned Aurora Stadium topology, routes, scenarios, terms
scripts/                 Seed, secret scan, server, and verification utilities
reports/                 Generated verification evidence
.github/workflows/       PostgreSQL/Redis CI and browser golden-flow workflow
```

## Run with Docker Compose

### Prerequisites

- Docker Desktop or Docker Engine with Compose
- Optional `GEMINI_API_KEY` for live generation

```bash
cp .env.example .env
# Set a strong SECRET_KEY in .env. Add GEMINI_API_KEY only for a live model run.
docker compose up --build
```

Open:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8001`
- OpenAPI: `http://localhost:8001/docs`

The backend entrypoint applies Alembic migrations and idempotently seeds reference data before starting.

## Local development

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:54321/crowdcue'
export REDIS_URL='redis://localhost:63791/0'
alembic -c backend/alembic.ini upgrade head
python -m scripts.seed_database
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8001`.

## Verification

```bash
# Linux/macOS
./scripts/verify.sh

# Windows PowerShell
./scripts/verify.ps1
```

Manual individual gates:

```bash
python scripts/secret-scan.py
black --check backend/app backend/tests backend/alembic scripts
isort --check-only backend/app backend/tests backend/alembic scripts
flake8 backend/app backend/tests backend/alembic scripts
mypy --explicit-package-bases backend/app
pytest backend/tests -q --cov=backend.app --cov-branch

cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
npm audit --audit-level=moderate
npm run test:e2e
```

With a running backend, verify the complete API flow:

```bash
python scripts/verify_golden_flow.py \
  --base-url http://127.0.0.1:8001 \
  --output reports/golden-flow-http.json
```

See [TESTING.md](TESTING.md) and [reports/VERIFICATION_REPORT.md](reports/VERIFICATION_REPORT.md) for the evidence matrix and environment limitations.

## Security

Never commit or upload `.env`, API keys, virtual environments, dependencies, browser reports, or runtime logs. Run the secret scanner before every release. See [SECURITY.md](SECURITY.md).

## Demo

Use [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the three-minute Gate C narrative.
