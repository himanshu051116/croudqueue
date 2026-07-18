# Security Notes

CrowdCue is a hackathon prototype with production-oriented safety boundaries, not a certified or production-authorized stadium system.

## Secrets

- Gemini calls are server-side only.
- `.env` and `backend/.env` are forbidden in release archives.
- Do not commit API keys, OAuth secrets, private keys, database passwords, virtual environments, dependency directories, or logs.
- Run `python scripts/secret-scan.py` before committing or packaging.
- Rotate any real credential that was ever included in an uploaded or shared archive, even if the file was later deleted.

## Runtime configuration

- Production rejects the development secret key.
- Production rejects demo fault injection.
- Wildcard CORS origins are rejected.
- SQLite is available only when both `ENVIRONMENT=test` and `ALLOW_SQLITE_TESTS=true` are set.
- Containers run as non-root users.

## Application controls

- Run commands are scoped by a session identifier; full identity/SSO is outside the hackathon scope.
- Candidate selection rejects deterministic vetoed candidates.
- Approval is impossible before semantic and simulation preflight pass.
- Approval and publication bind to a server-recomputed bundle hash.
- Publication is simulated and every delivery is persisted.
- External request IDs are hashed before public provenance exposure.
- API errors expose safe messages; raw provider responses and request headers are not logged.

## Known security limitations

- The session UUID is not enterprise authentication.
- There is no MFA, SSO, WAF, SIEM, KMS, penetration-test certification, or production incident-response process.
- The outbox claiming contract is implemented, but a complete production dispatcher/dead-letter operations service remains beyond the Golden Flow scope.
