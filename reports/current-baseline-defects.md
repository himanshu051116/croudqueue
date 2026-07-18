# Current baseline defects (2026-07-18)

Fresh verification of the uploaded source found:

- PostgreSQL used a fixed `pool_size=10` and `max_overflow=20`, unsafe per
  autoscaled function instance.
- Readiness failed whenever Redis was absent even though the Golden Flow writes
  delivery events transactionally to PostgreSQL and no synchronous Redis worker
  is required.
- `.env.example` enabled deliberate fault injection by default.
- No Vercel service/build configuration preserved both the root-level Python
  import context and root-level reference data.
- No deployed capability check read and hashed all required reference JSON.
- The test database hardcoded Unix `/tmp`, preventing pytest on Windows.
- Strict mypy failed on the Windows event-loop policy lookup.

Environment limitations observed during this verification:

- Python 3.12 was not installed locally; checks ran under Python 3.14.4 while
  deployment is pinned to 3.12.
- The npm package gateway repeatedly timed out downloading the exact locked
  Vite tarball, so frontend dependency-based gates could not run.
- No Vercel CLI/authentication, managed `DATABASE_URL`, or browser binary was
  available. Deployment, managed migrations, and deployed smoke tests were not
  executed.
