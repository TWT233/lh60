# LH60 Passive FFC Keyboard Implementation Plan

> **For agentic workers:** implement task-by-task from the current pushed
> `integration/mcu-tail-ffc` state after Tasks 0-3. Use one task branch and
> one task worktree per task. Steps use checkbox syntax for tracking.

**Goal:** finish the LH60 repository as one passive keyboard board with 75
switches, 70 diodes, and one `C2856805` FFC connector, with no in-repo MCU or
tail deliverable.

**Current baseline:** Tasks 0-3 are already completed on
`origin/integration/mcu-tail-ffc`. Task 0 depends on deployed Konnect custom
rule support at commit `f27cc8d`; Tasks 1-3 established the 24-pin connector
contract, project-local `C2856805` library, and passive main-schematic
direction.

**Architecture:** The remaining implementation is serial because one shared
root KiCad project and one shared `lh60.kicad_pcb` artifact are involved. The
contract/library work can precede PCB work, but once the root PCB is mutated,
all subsequent tasks depend on that exact board state.

**Tech Stack:** Python 3 standard library and `unittest`; KiCad 10;
Konnect MCP/CLI with deployed custom-rule support from `f27cc8d`; `xvfb-run -a`
for headless PCB IPC; Markdown/JSON/SVG/3D/manufacturing evidence.

## Global Constraints

- The only integration branch is `integration/mcu-tail-ffc`, checked out at
  `.worktree/mcu-tail-ffc/lh60`; the root checkout remains a clean `master`
  mirror.
- Create one task branch and one task worktree per task from the current pushed
  integration branch. Merge verified work with `--no-ff` into integration,
  rerun the integration gate there, and push integration before the next task.
- Every task must be independently reviewable and revertible. Commit and push
  after each completed task.
- Never text-edit `*.kicad_sch`, `*.kicad_pcb`, `*.kicad_pro`, `*.kicad_sym`,
  `*.kicad_mod`, `sym-lib-table`, or `fp-lib-table`.
- All schematic/PCB/library writes must go through Konnect or KiCad-aware IPC.
- KiCad PCB IPC and AppImage-backed checks are serialized on this host. Do not
  run parallel PCB mutation sessions.
- Existing deployed Konnect prerequisite `f27cc8d` is assumed present and must
  be cited where the exact `0.20 mm` same-footprint clearance exception is used.
- The release target is single-board `PROTOTYPE_READY`, not mass-production
  approval.

## File and Interface Map

| Responsibility | Files |
|---|---|
| Passive connector contract cleanup | `tools/lh60_design/interconnect.py`, `tools/verify_interconnect_contract.py` |
| Root project generator cleanup | `tools/lh60_design/project.py`, `tools/verify_project_contract.py` |
| Main schematic acceptance remains active | `tools/lh60_design/schematic.py`, `tools/check_schematic_acceptance.py`, `tools/verify_schematic_contract.py`, `tools/verify_schematic_acceptance.py`, `tools/verify_schematic_apply.py`, `lh60.kicad_sch` |
| Main PCB sync and placement | `tools/lh60_design/pcb.py`, `tools/sync_debug_connectors.py`, `tools/verify_pcb_sync.py`, `lh60.kicad_pcb` |
| Main PCB routing and acceptance | `tools/check_pcb_acceptance.py`, `tools/verify_pcb_acceptance.py`, `docs/reports/**`, `lh60.kicad_pcb` |
| External-adapter protocol and checker | `docs/external-adapter-interface.md`, `tools/check_prototype_acceptance.py`, `tools/verify_prototype_acceptance.py`, `docs/reports/passive-ffc-prototype-validation.md` |
| Single-board manufacturing package | `tools/export_manufacturing.py`, `tools/verify_manufacturing_package.py`, `docs/manufacturing/passive-ffc-release.*`, active baseline docs |

## Dependency Graph

```text
Task 1 contract/project cleanup
    |
    v
Task 2 main PCB sync + connector placement gate
    |
    v
Task 3 main PCB routing + acceptance
    |
    v
Task 4 external-adapter interface + prototype protocol/checker
    |
    v
Task 5 single-board prototype manufacturing package + final whole-branch review
```

Task 5 may embed the final whole-branch review, or split that review as a final
sub-step if the verification surface grows. No remaining PCB-writing tasks may
run in parallel because they share `lh60.kicad_pcb`.

## Remaining Tasks

### Task 1: MCU-agnostic contract and project cleanup

**Branch/worktree:** `task/passive-ffc-u1-contract-cleanup` at
`.worktree/passive-ffc-u1-contract-cleanup/lh60`

**Files:**
- Modify: `tools/lh60_design/interconnect.py`
- Modify: `tools/verify_interconnect_contract.py`
- Modify: `tools/lh60_design/project.py`
- Modify: `tools/verify_project_contract.py`
- Modify owned active tests that still require active MCU artifacts in the same
  task's write scope

**Interfaces:**
- Remove `matrix_gpio_map` from `InterboardContract`
- Remove MCU-tail/MIF-specific state from the passive contract
- Ensure future project generation does not require or register `lh60-mcu`
- Treat stale existing `sym-lib-table`/`fp-lib-table` registrations as legacy
  nonfunctional state unless a safe Konnect unregister API exists in-task

- [ ] **Step 1: Create the task worktree**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/passive-ffc-u1-contract-cleanup \
  .worktree/passive-ffc-u1-contract-cleanup/lh60 \
  origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write failing RED updates for the passive contract**

Update `tools/verify_interconnect_contract.py` so it still freezes:

- exact `1..24` pin map;
- exact connector identity;
- exact prohibited-net set;
- `J1.23` as `None`;
- passive reversal invariant;
- cable geometry fields that remain keyboard-side requirements.

But it must now fail if:

- `InterboardContract` exposes `matrix_gpio_map`;
- the contract exposes tail-only MIF approval fields not needed for the passive
  keyboard repo;
- the old RP2040 mapping is treated as normative instead of legacy-only.

Update `tools/verify_project_contract.py` to fail unless:

- future project generation does not require `lib/lh60-mcu`;
- future project generation does not register `lh60-mcu`;
- generated project tables can still register the active passive libraries;
- active outputs are MCU-free.

Remove or update obsolete active-MCU expectations in owned files rather than
leaving them skipped.

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_interconnect_contract tools.verify_project_contract
```

Expected: failures proving the contract and project generator still encode MCU
assumptions.

- [ ] **Step 4: Implement GREEN**

Implement the passive cleanup in the owned Python files only. Do not direct-edit
existing `sym-lib-table` or `fp-lib-table`; if a safe unregister capability is
absent, leave existing checked-in registrations as legacy state and document
that only future project generation is cleaned.

- [ ] **Step 5: Run focused and broad regression**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_interconnect_contract tools.verify_project_contract
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
git diff --check
```

- [ ] **Step 6: Commit, push, merge, and push integration**

```bash
git add tools/lh60_design/interconnect.py \
  tools/verify_interconnect_contract.py \
  tools/lh60_design/project.py \
  tools/verify_project_contract.py
git commit -m "refactor: make passive FFC contract MCU-agnostic"
git push -u origin task/passive-ffc-u1-contract-cleanup
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/passive-ffc-u1-contract-cleanup
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_interconnect_contract tools.verify_project_contract
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

### Task 2: Main PCB sync plus connector placement candidate and visual gate

**Branch/worktree:** `task/passive-ffc-u2-main-pcb-sync` at
`.worktree/passive-ffc-u2-main-pcb-sync/lh60`

**Files:**
- Modify: `tools/lh60_design/pcb.py`
- Modify: PCB sync entrypoint under `tools/`
- Modify: `tools/verify_pcb_sync.py`
- Modify through KiCad-aware tools: `lh60.kicad_pcb`
- Add/update evidence under `docs/reports/`

**Interfaces:**
- Root board must converge to exact `146` footprints:
  - `75` switches
  - `70` diodes
  - `1` connector `J1`
- Remove `U1` and `J2..J6` from the active root board
- Preserve board outline, socket placements, and board identity
- Derive exact `J1` pose via bounded candidate search plus visual/courtyard/access checks

- [ ] **Step 1: Create the task worktree**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/passive-ffc-u2-main-pcb-sync \
  .worktree/passive-ffc-u2-main-pcb-sync/lh60 \
  origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write failing RED updates for PCB sync and placement**

Update `tools/lh60_design/pcb.py` and `tools/verify_pcb_sync.py` so the frozen
inventory, sync expectations, and placement logic fail unless:

- active board references are exactly the passive set;
- no `U1`, `J2`, `J3`, `J4`, `J5`, or `J6` remain active;
- `J1` is the `C2856805` connector, not the old 3-pin power header;
- bounded placement search plus explicit visual approval binds the accepted
  pose before production mutation;
- placement gates enforce:
  - accessible board-edge mouth;
  - body/lands/keepout inside outline;
  - `6 mm` stiffener insertion zone clear;
  - first bend outside stiffener;
  - `0.50 mm` copper-to-edge minimum.

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_pcb_sync
```

- [ ] **Step 4: Implement the passive sync and placement gate**

Use only Konnect/KiCad-aware flows. Do not raw-edit `lh60.kicad_pcb`.

Serialized session outline:

```bash
xvfb-run -a python -m tools.sync_debug_connectors --dry-run
xvfb-run -a python -m tools.sync_debug_connectors --apply
```

Produce a candidate-placement artifact and a visual approval record under
`docs/reports/` before committing the accepted `J1` pose to the production
board.

- [ ] **Step 5: Run GREEN verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync
xvfb-run -a python tools/check_pcb_acceptance.py --phase sync
git diff --check
```

- [ ] **Step 6: Commit, push, merge, and push integration**

```bash
git add tools/lh60_design/pcb.py \
  tools/sync_debug_connectors.py \
  tools/verify_pcb_sync.py \
  docs/reports \
  lh60.kicad_pcb
git commit -m "feat(pcb): sync passive FFC board inventory"
git push -u origin task/passive-ffc-u2-main-pcb-sync
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/passive-ffc-u2-main-pcb-sync
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

### Task 3: Main PCB routing and single-board acceptance

**Branch/worktree:** `task/passive-ffc-u3-main-pcb-routing` at
`.worktree/passive-ffc-u3-main-pcb-routing/lh60`

**Files:**
- Modify: `tools/check_pcb_acceptance.py`
- Modify: `tools/verify_pcb_acceptance.py`
- Modify through KiCad-aware tools: `lh60.kicad_pcb`
- Add/update evidence under `docs/reports/`

**Interfaces:**
- Route matrix nets and `J1`;
- establish GND reference and any required zones;
- preserve exact `C2856805` clearance exception from deployed Konnect support;
- require zero DRC errors and zero unconnected items;
- require render/3D/DFM outputs for the single root board only.

- [ ] **Step 1: Create the task worktree**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/passive-ffc-u3-main-pcb-routing \
  .worktree/passive-ffc-u3-main-pcb-routing/lh60 \
  origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write failing RED updates for single-board acceptance**

Update `tools/verify_pcb_acceptance.py` and `tools/check_pcb_acceptance.py` so
they fail unless:

- only the passive-board connector endpoints are expected;
- no active MCU or debug-header assumptions remain;
- DRC and unconnected counts must both be zero;
- manufacturing/DFM checks are single-board and root-board only.

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_acceptance
```

- [ ] **Step 4: Route through one serialized KiCad/ Konnect session**

Use `xvfb-run -a` and one serialized PCB mutation session. Refill zones, route
matrix/FPC nets, and save through sanctioned tools only.

- [ ] **Step 5: Run GREEN acceptance**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_acceptance
xvfb-run -a python tools/check_pcb_acceptance.py --phase final
git diff --check
```

Acceptance must include:

- zero DRC errors;
- zero unconnected items;
- exact same-footprint `0.20 mm` connector-pad exception and `0.25 mm` general
  clearance;
- root-board SVG, 3D, and DFM evidence.

- [ ] **Step 6: Commit, push, merge, and push integration**

```bash
git add tools/check_pcb_acceptance.py \
  tools/verify_pcb_acceptance.py \
  docs/reports \
  lh60.kicad_pcb
git commit -m "feat(pcb): route passive FFC keyboard board"
git push -u origin task/passive-ffc-u3-main-pcb-routing
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/passive-ffc-u3-main-pcb-routing
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_acceptance
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

### Task 4: Generic external-adapter interface plus prototype protocol and checker

**Branch/worktree:** `task/passive-ffc-u4-adapter-protocol` at
`.worktree/passive-ffc-u4-adapter-protocol/lh60`

**Files:**
- Create: `docs/external-adapter-interface.md`
- Create: `tools/check_prototype_acceptance.py`
- Create: `tools/verify_prototype_acceptance.py`
- Create: `docs/reports/passive-ffc-prototype-validation.md`

**Interfaces:**
- The adapter chooses its MCU pins; the repo does not freeze them;
- the protocol defines continuity and matrix-scan evidence schema only;
- physical evidence remains `INCOMPLETE` unless user-provided hardware results
  are supplied.

- [ ] **Step 1: Create the task worktree**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/passive-ffc-u4-adapter-protocol \
  .worktree/passive-ffc-u4-adapter-protocol/lh60 \
  origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write RED tests and schema expectations**

Freeze a strict schema that requires:

- adapter identity and operator metadata;
- cable identity;
- explicit pin-1 observation statement;
- continuity results for all 24 positions;
- matrix scan results for all 70 logical nodes;
- status fields that remain `INCOMPLETE` without real hardware evidence.

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_prototype_acceptance
```

- [ ] **Step 4: Implement the checker and docs**

Document the external-adapter interface and the prototype protocol. The docs
may include the old RP2040 mapping only as a non-normative example.

The checker must never fabricate evidence. If the hardware payload is absent,
it must report an incomplete external gate, not a pass.

- [ ] **Step 5: Run GREEN**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_prototype_acceptance
git diff --check
```

- [ ] **Step 6: Commit, push, merge, and push integration**

```bash
git add docs/external-adapter-interface.md \
  tools/check_prototype_acceptance.py \
  tools/verify_prototype_acceptance.py \
  docs/reports/passive-ffc-prototype-validation.md
git commit -m "docs: define passive FFC adapter protocol"
git push -u origin task/passive-ffc-u4-adapter-protocol
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/passive-ffc-u4-adapter-protocol
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_prototype_acceptance
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

### Task 5: Single-board prototype manufacturing package and final review

**Branch/worktree:** `task/passive-ffc-u5-release` at
`.worktree/passive-ffc-u5-release/lh60`

**Files:**
- Modify: `tools/export_manufacturing.py`
- Modify: `tools/verify_manufacturing_package.py`
- Create: `docs/manufacturing/passive-ffc-release.md`
- Create: release artifacts and hashes for the root board only
- Update: active baseline docs such as `docs/current-baseline.md`

**Interfaces:**
- root board only;
- JLCPCB-oriented outputs;
- BOM/PnP reflect the passive board only;
- release status is `PROTOTYPE_READY`, not mass-production approved;
- final whole-branch review is required before completion.

- [ ] **Step 1: Create the task worktree**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/passive-ffc-u5-release \
  .worktree/passive-ffc-u5-release/lh60 \
  origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write RED release tests**

Fail unless:

- only root-board manufacturing outputs exist;
- BOM/PnP exclude inactive MCU artifacts;
- release metadata includes hashes and exact status `PROTOTYPE_READY`;
- external hardware gate is clearly marked incomplete/blocking for
  mass-production approval.

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_manufacturing_package
```

- [ ] **Step 4: Export the single-board package**

Use sanctioned KiCad/Konnect tooling only. Produce the root-board fabrication,
assembly, and documentation outputs plus hashes.

- [ ] **Step 5: Run final review and GREEN verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
xvfb-run -a python tools/check_pcb_acceptance.py --phase final
git diff --check
```

Final review must confirm:

- active schematic/PCB/BOM/PnP are passive-board only;
- no active MCU or tail deliverable remains;
- release docs and baseline docs agree on `PROTOTYPE_READY`.

- [ ] **Step 6: Commit, push, merge, and push integration**

```bash
git add tools/export_manufacturing.py \
  tools/verify_manufacturing_package.py \
  docs/manufacturing/passive-ffc-release.md \
  docs/current-baseline.md
git commit -m "feat: export passive FFC prototype package"
git push -u origin task/passive-ffc-u5-release
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/passive-ffc-u5-release
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_manufacturing_package
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

## Execution Notes

- All remaining PCB work is serialized because `lh60.kicad_pcb` is shared.
- The plan intentionally does not direct-edit existing checked-in library tables
  because Konnect lacks a safe unregister API today.
- If a future task adds a safe unregister/read-modify-write API through
  Konnect, that cleanup can remove stale `lh60-mcu` registrations explicitly.
