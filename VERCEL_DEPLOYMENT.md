# Vercel deployment

CrowdCue uses one Vercel project with Services: the existing Vite application is
served from `frontend/`, while the FastAPI service keeps the repository root as
its build context and imports `backend.app.main:app`. This preserves root-level
`reference_data/` and `requirements-runtime.txt` and keeps browser requests on
the same-origin `/api` path.

## Required environment variables

- `DATABASE_URL`
- `SECRET_KEY`
- `ENVIRONMENT=production`
- `ENABLE_DEMO_FAULT_INJECTION=false`
- `REDIS_REQUIRED=false` unless a tested managed Redis is intentionally required

Optional tuning and integrations: `DATABASE_POOL_SIZE`,
`DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_TIMEOUT_SECONDS`,
`DATABASE_POOL_RECYCLE_SECONDS`, `REDIS_URL`, `GEMINI_API_KEY`, and the existing
Gemini timeout/retry variables. Never use localhost service URLs in Vercel.

Migrations and `scripts/seed_database.py` are explicit release operations. They
must run against an empty or backed-up managed PostgreSQL database before the
preview Golden Flow; neither runs during import, build, cold start, or request.

Protected demo previews may set `ENVIRONMENT=development` and
`ENABLE_DEMO_FAULT_INJECTION=true`; they must be access-controlled and visibly
treated as a deliberate demonstration defect. Production rejects that setting.
