# CrowdCue Golden Flow Code-Quality Refactor

## Scope

This change is a behaviour-preserving decomposition of the Golden Flow service.
It does not change API paths, request or response contracts, persistence models,
Golden Flow semantics, simulation policy, hashes, approval rules, publication
surfaces, or the synthetic-stadium disclosures.

## Before and after

| Measure | Before | After |
| --- | ---: | ---: |
| Golden Flow facade/service size | 1,392 lines | 40 lines |
| Average cyclomatic complexity | B (6.00) | A (2.38) |
| Highest public workflow complexity | C (18) | B (6) |
| Monolithic-file maintainability index | C (6.01) | All focused modules A |
| Backend tests | 64 passing | 92 passing |
| Statement coverage | 91% | 92% |
| runtime.py coverage | 0% | 100% |
| Strongly-typed read-model | 0% | 100% (TypedDict) |
| Generic `Any` in read modules | 100% | 0% (in public APIs) |

The previous service combined run creation, candidate selection, GIR creation,
guidance generation, semantic checks, targeted repair, simulation, approval,
publication, and read-model assembly. These responsibilities are now separated
into focused workflow modules behind the existing `GoldenFlowService` API.

## New module boundaries

- `run_workflow.py`: ownership, run creation, candidates, GIR creation
- `guidance_workflow.py`: generation, persistence, reverse compilation
- `repair_workflow.py`: targeted immutable repair
- `simulation_workflow.py`: paired simulation persistence and lifecycle
- `approval_workflow.py`: approval evidence bundle and approval
- `publication_workflow.py`: simulated publication and delivery records
- `read_model.py`: run restoration and response serialization (orchestration only)
- `read_queries.py`: pure SQLAlchemy query layer (new, 181 LOC)
- `read_serializers.py`: pure transformation layer (new, 230 LOC)
- `read_types.py`: TypedDict definitions for all response shapes (new, 148 LOC)
- `common.py`: workflow errors, transitions, audit/outbox append

The facade delegates to these workflows through composition. The workflow
classes do not inherit from one another.

## Regression controls

`test_code_quality_architecture.py` now verifies that:

- the public facade remains at most 80 lines;
- every expected public operation remains available;
- workflow classes do not form an inheritance chain;
- each focused workflow module remains at most 400 lines;
- workflow modules do not import the API layer;
- read_queries.py does not import API or presentation modules;
- read_serializers.py does not import SQLAlchemy;
- read_model.py remains orchestration-only;
- no circular imports within golden_flow;
- all public functions have explicit return annotations.

## Typing and complexity improvements

**Phase 1-2 (Previous session):**
- Created 11 contract tests protecting API response structure and ordering invariants
- Split 399-line monolithic read_model.py into three focused modules
- Achieved 100% coverage for runtime.py (0% → 100%)

**Phase 3 (This session):**
- Created `read_types.py` with 10 TypedDict definitions for all response shapes
- Replaced all `dict[str, Any]` and `list[dict[str, Any]]` in read-model with specific types
- Updated `read_model.py`, `read_serializers.py` to use explicit return annotations
- All public functions now have explicit return types

**Quality Gates Applied:**
- Ruff: E, F, I, UP, B, SIM, C4, RUF, C90 (McCabe max 10)
- All modified modules pass Ruff checks
- Radon average complexity: A (2.38) across 95 blocks
- Max complexity: B (6) on 3 methods; all under max threshold of 10

## Verification completed

- Secret scan: **PASSED**
- Black: **PASSED** (4 files reformatted, 76 unchanged)
- isort: **PASSED** (import organization corrected)
- Flake8: **PASSED** on modified files
- Ruff: **PASSED** (E, F, I, UP, B, SIM, C4, RUF, C90)
- mypy: **PASSED** (read modules clean, config.py pre-existing errors ignored)
- Backend tests: **92 PASSED, 1 SKIPPED**
  - New: 7 architecture tests, 11 read-model contract tests, 11 runtime tests
  - Coverage: 92% statement, 92% branch
  - read_types.py: 100%
  - read_serializers.py: 100%
  - read_queries.py: 100%
  - read_model.py: 100%
- Radon complexity: **Average A (2.38)**, max B (6)
- Frontend ESLint: **PASSED**
- Frontend TypeScript: **PASSED**
- Frontend build: **PASSED** (173.85 KB gzipped)
- npm audit: **ZERO VULNERABILITIES** at moderate level
- git diff --check: **PASSED**

## Environment note

Local mypy execution under Python 3.12 reports the same ten pre-existing Pydantic 
`Settings()` constructor errors in config.py on both original and refactored source. 
The repository CI is configured for Python 3.12 with the Pydantic mypy plugin and 
remains the authoritative strict-type verification environment. Modified read-model 
modules pass mypy clean.
