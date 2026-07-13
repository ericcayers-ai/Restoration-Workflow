# Phase 5 — Smart Orchestration v2 Decision

**Date:** 2026-07-13  
**Decision:** Keep the v1 heuristic degradation analyzer.

## Usage data collected

The backend records `routing_override` events when Studio Mode users change the
auto-picked pipeline before running (`core/router_telemetry.py`). As of this
release, insufficient production usage exists to justify training or adopting a
learned router (Restore-R1, RAR, RL-Restore remain code-less).

## Rationale

Phase 5 acceptance allows either a measurably better router *or* an explicit
decision to keep v1 with supporting data. The v1 rule table continues to route
competently on measured degradation; source-format families are covered by the
sixteen built-in presets (Phase 4.5.3).

## Revisit when

- `routing_override` rate exceeds 25% on a representative corpus, or
- Restore-R1 / RAR publish usable code and weights with clear licenses.
