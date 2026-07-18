# CrowdCue 2.0 Architecture

## Trust boundary

```text
Structured venue state + confirmed operational intent
                    ↓
Configuration-driven candidates and deterministic vetoes
                    ↓
Operator selects a viable candidate
                    ↓
Authoritative immutable GIR
                    ↓
Gemini multilingual rendering or deterministic fallback
                    ↓
Schema validation and final text rendering
                    ↓
Independent EN/ES/FR reverse compilation
                    ↓
Bidirectional semantic comparison
                    ↓
Accessibility and active-instruction invariants
                    ↓
200 shared-condition paired aggregate-flow samples
                    ↓
PASS / REVIEW / BLOCK
                    ↓
Server-recomputed evidence bundle + human approval
                    ↓
Simulated multichannel publication + audit/outbox evidence
```

GenAI never owns venue truth, candidate viability, semantic pass/fail, simulation policy, approval eligibility, or publication state.

## Authoritative state

- PostgreSQL is the source of truth for sessions, snapshots, runs, candidates, GIR versions, variants, diagnostics, simulation, approval, publication, and audit.
- Redis is a transient readiness and future dispatch coordination dependency. Losing Redis must not change authoritative run state.
- Browser state is a projection of backend state. The current run identifier is retained in session storage only to restore the authoritative run after refresh.

## Generation paths

### Live model path

One server-side Interactions API request returns all six EN/ES/FR Fan App and PA variants. The request uses a structured JSON schema and exact canonical semantic anchors. Returned text is not trusted until reverse compilation and semantic comparison pass.

### Controlled fallback path

When no key is configured or live generation fails, canonical deterministic templates produce the same six variants. Fallback output passes through the identical compiler and analyser. Provenance records provider, model target, request counts, latency, and safe error code.

### Demo fault path

When explicitly enabled in non-production configuration, a named demonstration fault removes only the Spanish Fan App mobility-assistance clause. The system records the fault, blocks preflight, and prevents approval. Targeted repair creates an immutable second version and preserves the other five variant hashes and every unrelated Spanish clause.

## Workflow

```text
DRAFT
  └─ CANDIDATE_SELECTED
       └─ GUIDANCE_VERIFYING
            ├─ PREFLIGHT_BLOCKED ── repair ──> GUIDANCE_VERIFYING
            └─ SEMANTIC_PASSED
                 └─ SIMULATION_RUNNING
                      ├─ PREFLIGHT_BLOCKED
                      └─ PREFLIGHT_PASSED
                           └─ APPROVED
                                └─ PUBLISHING
                                     └─ PUBLISHED
```

Invalid transitions return HTTP 409.

## Integrity

- Hashes use domain-separated, canonical JSON encoded as UTF-8.
- Approval binds the run/version, candidate, GIR, snapshot, ordered current variants, semantic comparison, diagnostics, simulation result, and versioned reference/configuration contracts.
- Approval and publication recompute the bundle while holding a database row lock.
- Audit events use a per-session sequence and previous-hash chain and are appended in the same transaction as outbox evidence.

## Publication matrix

- Fan App: EN, ES, FR verified Fan App variants.
- PA: EN, ES, FR verified PA variants.
- Signage: EN, ES, FR deterministically derived from verified Fan App variants.
- Volunteer Device: one deterministic operations instruction derived from the GIR.

All deliveries are simulated and persisted individually.
