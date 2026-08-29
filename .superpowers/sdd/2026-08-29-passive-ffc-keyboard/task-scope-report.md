# Task Scope Report: Passive FFC Scope Revision

## Scope

- Task branch/worktree: `task/passive-ffc-scope` at
  `.worktree/passive-ffc-scope/lh60`
- Integration branch/worktree: `integration/mcu-tail-ffc` at
  `.worktree/mcu-tail-ffc/lh60`
- Goal: add the new passive-only scope docs, mark the prior dual-board docs as
  superseded after completed Tasks 0-3, and leave their historical content
  otherwise intact.

## Changes

- Added `docs/superpowers/specs/2026-08-29-passive-ffc-keyboard-design.md`
- Added `docs/superpowers/plans/2026-08-29-passive-ffc-keyboard.md`
- Added a short superseded notice at the top of:
  - `docs/superpowers/specs/2026-08-29-external-mcu-ffc-tail-design.md`
  - `docs/superpowers/plans/2026-08-29-external-mcu-ffc-tail.md`

## Frozen Direction

- Repository deliverable is one passive root LH60 board only.
- Exact `J1` 24-pin map remains frozen.
- External MCU mapping is non-normative and must be removed from the active
  passive contract in a later task.
- Keyboard-side connector identity, geometry, clearance stack, and placement
  gates remain active.
- No tail project, tail PCB, tail MIF, or tail manufacturing package remains in
  scope.
- Release target is single-board `PROTOTYPE_READY`; hardware-backed external
  continuity/matrix-scan evidence stays an external incomplete gate.

## Review Notes

- The new spec and plan were checked for contradictions against the requested
  scope and the already-completed Tasks 0-3 state.
- The old spec and plan were only annotated as superseded; their historical
  body text was not rewritten.
