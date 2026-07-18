# CrowdCue 2.0 — Phase 2 Hardening Tasks

## Database & Migrations
- [/] Create migration 002_hardening.py
- [ ] Update run.py model definitions (structured intent, snapshot fields, rejections)
- [ ] Run Alembic migration upgrade on database

## Reference Data
- [ ] Update reference_data/venue.json (authoritative nodes, Gate D, Plaza, Transit, Shuttle, Concourses, Lift D2, coords)
- [ ] Update reference_data/routes.json (complete routes)
- [ ] Update reference_data/scenarios.json (configuration-driven schema)

## Backend Logic & Services
- [ ] Update domain/venue.py (coordinates, parsing)
- [ ] Update domain/candidate.py (generic rules evaluator, rank, route/edge/asset rejections)
- [ ] Update services/venue_service.py (configuration-driven candidate generation, deterministic ordering with stable tie-breaker)
- [ ] Update api/venue.py (endpoints, session verification)

## Frontend Refactoring & Modularity
- [ ] Create ScenarioTriggerPanel.tsx (modular scenario trigger controls)
- [ ] Create IntentEditor.tsx (modular structured intent editor)
- [ ] Create CandidateList.tsx (viable and rejected candidate list)
- [ ] Update VenueMap.tsx (dynamic backend coords, accessibility, text alternatives)
- [ ] Update App.tsx (compose product shell)

## Testing & Verification
- [ ] Create test_hardening.py (scenario config addition, reproducibility check, session boundary enforcement)
- [ ] Run tests and verify 100% green
- [ ] Generate branch and line coverage reports
- [ ] Run Docker stack smoke test check
