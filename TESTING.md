# Testing and Verification

## Test layers

### Credential-free backend suite

The normal test suite uses an explicitly enabled test-only SQLite database for fast feedback when no PostgreSQL service is available. Production configuration rejects SQLite. In CI, `DATABASE_URL` is supplied by PostgreSQL 17, so the same suite runs against PostgreSQL.

Coverage includes:

- reference-data immutability and venue-scoped identifiers;
- topology and route validation;
- deterministic candidate vetoes and ordering;
- optimistic concurrency;
- normalized variant persistence;
- current Gemini Interactions request/response parsing with mocked transport;
- 429 retry and safe error normalization;
- six-variant fallback equivalence;
- semantic mutation matrix;
- demo fault gating and protected-cohort omission;
- immutable targeted repair isolation;
- paired simulation reproducibility and protected-route veto;
- state transition enforcement;
- stale approval bundle rejection;
- publication delivery persistence;
- session ownership;
- audit chain verification and transactional outbox behavior.

### PostgreSQL CI

The backend CI job starts PostgreSQL 17 and Redis 7, applies all Alembic migrations, runs `alembic check`, seeds reference data, and executes the complete suite with coverage.

### Frontend static gates

- clean `npm ci`;
- ESLint with zero warnings;
- TypeScript no-emit check;
- production Vite build;
- npm vulnerability audit.

### Playwright golden flow

The CI browser job verifies:

1. Gate C scenario and full Aurora topology.
2. Candidate selection.
3. Six variants and deliberate Spanish omission.
4. blocking diagnostic and disabled approval.
5. targeted repair and version 2.
6. paired simulation PASS.
7. approval and simulated publication.
8. persisted publication evidence after page reload.
9. audit hash-chain indicator.
10. keyboard scenario operation, meaningful map text alternative, axe serious/critical gate, and 390 px overflow gate.

## Live Gemini verification

A live key is never required for deterministic product continuity or automated tests. A live evaluation must separately report model, attempts, successes, genuine variants, fallback variants, latency, and safe errors. Fallback must not be reported as live Gemini success.

## Current packaged evidence

Read `reports/VERIFICATION_REPORT.md` and `reports/VERIFICATION_REPORT.json`. They distinguish passed local gates from checks that require Docker, PostgreSQL, an unrestricted browser, a remote CI runner, or a live Gemini key.
