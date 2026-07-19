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
| Average cyclomatic complexity | B (6.00) | A (2.59) |
| Highest public workflow complexity | C (18) | A (4) |
| Monolithic-file maintainability index | C (6.01) | All focused modules A |
| Backend tests | 64 passing | 66 passing |
| Combined branch coverage | 83% | 85% |

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
- `read_model.py`: run restoration and response serialization
- `common.py`: workflow errors, transitions, audit/outbox append

The facade delegates to these workflows through composition. The workflow
classes do not inherit from one another.

## Regression controls

`test_code_quality_architecture.py` now verifies that:

- the public facade remains at most 60 lines;
- every expected public operation remains available;
- workflow classes do not form an inheritance chain;
- each focused workflow module remains at most 400 lines;
- workflow modules do not import the API layer.

## Verification completed

- Secret scan: passed
- Black: passed across backend application, tests, migrations, and scripts
- isort: passed across backend application, tests, migrations, and scripts
- Flake8: passed across backend application, tests, migrations, and scripts
- Backend tests: 66 passed
- Combined branch coverage: 85%
- Frontend ESLint: passed
- Frontend TypeScript check: passed
- Frontend production build: passed
- npm audit at moderate severity: zero vulnerabilities
- `git diff --check`: passed

## Environment note

Local mypy execution under Python 3.13 reports the same ten Pydantic `Settings()`
constructor errors on both the original and refactored source. The repository CI
is configured for Python 3.12 with the Pydantic mypy plugin and remains the
authoritative strict-type verification environment.
