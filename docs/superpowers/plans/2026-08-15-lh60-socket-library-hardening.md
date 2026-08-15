# LH60 Socket Library Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the eight LH60 socket footprints into portable, electrically safe, assembly-aware footprints with real mechanical courtyards and reproducible KiCad regression coupons.

**Architecture:** All writes to KiCad source files go through Konnect MCP. This repository only consumes Konnect APIs; Konnect development and deployment are explicitly outside this plan. Python `unittest` tests inspect the resulting library and invoke KiCad CLI for parser and DRC verification.

**Tech Stack:** Rust, Konnect MCP over stdio, KiCad 10 CLI, Python 3 `unittest`, Shapely 2.x.

## Global Constraints

- Do not directly edit `.kicad_mod`, `.kicad_pcb`, `.kicad_pro`, `fp-lib-table`, or other KiCad source files.
- Gateron LP and Choc V1 contact pads in a dual footprint must expose the same logical pad numbers `1` and `2`.
- Courtyards use `B.CrtYd`, 0.05 mm stroke, no fill, and enclose the union of the physical socket and complete land pattern with 0.25 mm clearance.
- Keycap envelopes use `Dwgs.User`, not production silkscreen.
- Socket footprints are excluded from position files but remain in the BOM.
- Every commit message ends with `Co-authored-by: TRAE CLI <noreply@bytedance.com>`.
- Each completed unit is committed and pushed before the next unit starts.

## Units, Dependencies, and Contracts

| Unit | Deliverable | Dependency |
|---|---|---|
| U1 | LH60 library regression test harness | None |
| U2 | Dual-socket electrical pad-number contract | U1 failing electrical test |
| U3 | Mechanical graphics, courtyards, 3D models, assembly attributes | U1 failing mechanical tests; serial after U2 because files overlap |
| U4 | Portable library registration, clean coupon, conflict fixture, unified documentation | U2 and U3 final footprint contract |

### Shared Interfaces

- Konnect MCP is an external dependency. Before each KiCad mutation task, inspect the
  currently exposed `library` tool schemas and use only supported safe APIs.
- If a required mutation is not exposed, stop that KiCad mutation task without editing
  the protected file directly; continue only non-dependent LH60 work.
- `test/test_lh60_sockets.py`
  - `footprints()` returns the eight canonical `.kicad_mod` paths.
  - `run_kicad_cli(*args)` runs the configured `kicad-cli` and fails with captured output.
  - Tests read KiCad files only; they never write protected files.
- `test/generate_socket_coupons.py`
  - Speaks MCP JSON-RPC to Konnect.
  - Generates `socket-clean.kicad_pcb` and `socket-conflicts.kicad_pcb` only through Konnect tools.

---

### Task 1: Add LH60 Library Regression Tests

**Files:**
- Create: `test/test_lh60_sockets.py`

**Interfaces:**
- Consumes the eight canonical footprint paths and KiCad CLI.
- Produces tests for pad signatures, layers, courtyard extents, metadata, model paths, parseability, coupon DRC, and fixture DRC.

- [ ] **Step 1: Write failing tests**

Tests assert:

```python
self.assertEqual(dual_pad_numbers, {"1", "2"})
self.assertEqual(layer_counts["F.SilkS"], 0)
self.assertEqual(layer_counts["Dwgs.User"], 1)
self.assertGreaterEqual(layer_counts["B.Fab"], 1)
self.assertGreaterEqual(layer_counts["B.CrtYd"], 1)
self.assertTrue(metadata.exclude_from_pos_files)
self.assertTrue(existing_model_paths)
```

Also assert all seven Gateron-only footprints share identical pads and differ only in their `Dwgs.User` keycap rectangle.

- [ ] **Step 2: Verify red**

Run:

```bash
python -m unittest -v test.test_lh60_sockets
```

Expected: failures for Choc pad numbers, missing courtyard/fab/user graphics, metadata, models, and coupons.

- [ ] **Step 3: Commit the red harness**

Commit title: `test: add socket library regression contract`

---

### Task 2: Fix Dual-Socket Electrical Contract

**Files:**
- Modify through Konnect MCP: `lib/lh60-sockets/Gateron-LP-or-ChocV1-Hotswap-Socket-1U.kicad_mod`

**Interfaces:**
- Consumes the corresponding safe Konnect pad-renumbering API exposed at execution time.
- Produces three Gateron pad-1 blocks plus three Choc pad-1 blocks, and the equivalent six pad-2 blocks, all inheriting schematic nets automatically.

- [ ] **Step 1: Run only the electrical test and confirm red**

```bash
python -m unittest -v test.test_lh60_sockets.SocketElectricalContractTest
```

- [ ] **Step 2: Renumber through Konnect MCP**

Call:

```text
edit_footprint_pad(pad_number="3", new_number="1", match_all=true)
edit_footprint_pad(pad_number="4", new_number="2", match_all=true)
```

- [ ] **Step 3: Verify green and parseability**

```bash
python -m unittest -v test.test_lh60_sockets.SocketElectricalContractTest
kicad-cli fp export svg --output /tmp/lh60-socket-svg lib/lh60-sockets
```

- [ ] **Step 4: Commit and push**

Commit title: `fix(lib): share dual-socket electrical pads`

---

### Task 3: Add Mechanical, Assembly, and 3D Information

**Files:**
- Modify through Konnect MCP: `lib/lh60-sockets/*.kicad_mod`
- Modify: `test/test_lh60_sockets.py`

**Interfaces:**
- Consumes the corresponding safe Konnect graphics, metadata, and model APIs exposed at execution time.
- Produces complete `Dwgs.User`, `B.Fab`, `B.CrtYd`, metadata, attributes, and 3D model definitions.

- [ ] **Step 1: Confirm mechanical tests are red**

```bash
python -m unittest -v test.test_lh60_sockets.SocketMechanicalContractTest
```

- [ ] **Step 2: Generate exact courtyard polygons**

Use Shapely to union:

- physical plastic body,
- terminal rectangles,
- SMD pads and copper bridge rectangles,
- PTH annular rings,

then apply `buffer(0.25, join_style="round")`. Round output coordinates to 0.001 mm and simplify only when Hausdorff distance remains at or below 0.01 mm.

- [ ] **Step 3: Write graphics through Konnect**

For every footprint:

```text
set_footprint_graphics(layer="F.SilkS", mode="delete")
set_footprint_graphics(layer="Dwgs.User", mode="replace", graphics=[keycap rectangle])
set_footprint_graphics(layer="B.Fab", mode="replace", graphics=[socket bodies and G/C marks])
set_footprint_graphics(layer="B.CrtYd", mode="replace", graphics=[land-pattern-aware polygons])
```

- [ ] **Step 4: Set metadata and models through Konnect**

Set `attributes=["exclude_from_pos_files"]`.

Use model paths:

```text
../mxv2/Gateron_KS33_Hotswap.pretty/Gateron-KS33-Socket.step
../mxv2/Kailh_PG1353_Hotswap.pretty/Kailh-Choc-Socket-CPG135001S30.step
```

Gateron-only footprints receive the Gateron model. The dual footprint receives both models so the `Both` assembly state is visible; documentation records how to hide either model for single-socket assembly views.

- [ ] **Step 5: Verify**

```bash
python -m unittest -v test.test_lh60_sockets.SocketMechanicalContractTest
kicad-cli fp export svg --layers B.Fab,B.CrtYd,Dwgs.User --output /tmp/lh60-socket-svg lib/lh60-sockets
```

- [ ] **Step 6: Commit and push**

Commit title: `feat(lib): add socket assembly geometry`

---

### Task 4: Rebuild Portable Coupons and Documentation

**Files:**
- Create: `test/generate_socket_coupons.py`
- Create through Konnect MCP: `test/socket-clean.kicad_pro`
- Create through Konnect MCP: `test/socket-clean.kicad_pcb`
- Create through Konnect MCP: `test/socket-conflicts.kicad_pro`
- Create through Konnect MCP: `test/socket-conflicts.kicad_pcb`
- Modify through Konnect MCP: `test/fp-lib-table`
- Modify: `lib/lh60-sockets/README.md`
- Modify: `docs/socket-baseline.md`
- Modify: `docs/current-baseline.md`
- Modify: `docs/superpowers/specs/2026-08-15-socket-b-crtyd-design.md`
- Modify: `test/test_lh60_sockets.py`

**Interfaces:**
- Consumes final footprint library contract.
- Produces one zero-violation coupon and one expected-conflict fixture with machine-readable expected violation classes.

- [ ] **Step 1: Register portable libraries through Konnect**

Register these project-relative paths:

```text
${KIPRJMOD}/../lib/keysw-siderakb
${KIPRJMOD}/../lib/mxv2/Gateron_KS33_Hotswap.pretty
${KIPRJMOD}/../lib/lh60-sockets
${KIPRJMOD}/../lib/mxv2/Kailh_PG1353_Hotswap.pretty
```

- [ ] **Step 2: Generate coupons through Konnect**

`socket-clean` contains all eight canonical footprints separated so DRC must report zero errors, zero warnings, and zero unconnected items.

`socket-conflicts` contains named overlap cases for courtyard, copper/hole, and the historical 0.07 mm manufacturing tight point. Its test asserts exact violation types rather than expecting a green DRC.

- [ ] **Step 3: Update documentation**

Remove the obsolete “no courtyard” and rectangular-courtyard claims. Document:

- logical duplicate pad numbers,
- land-pattern-aware `B.CrtYd`,
- `Dwgs.User` keycap envelopes,
- `B.Fab` assembly markings,
- manual-solder/PnP exclusion,
- dual-socket 3D `Both` view and single-socket visibility workflow,
- coupon commands and real-world coupon requirement.

- [ ] **Step 4: Verify**

```bash
python -m unittest -v test.test_lh60_sockets
kicad-cli pcb drc --format json --output /tmp/socket-clean-drc.json test/socket-clean.kicad_pcb
kicad-cli pcb drc --format json --output /tmp/socket-conflicts-drc.json test/socket-conflicts.kicad_pcb
git diff --check
```

Expected:

- full unittest suite passes,
- clean coupon has zero violations,
- conflict fixture has only documented expected violation classes,
- no whitespace errors.

- [ ] **Step 5: Commit and push**

Commit title: `test: add reproducible socket coupons`

---

### Task 5: Final Integration Verification

**Files:**
- No new files.

- [ ] **Step 1: Fresh full verification**

```bash
rm -rf /tmp/lh60-socket-final-svg
python -m unittest -v test.test_lh60_sockets
kicad-cli fp export svg --output /tmp/lh60-socket-final-svg lib/lh60-sockets
test "$(find /tmp/lh60-socket-final-svg -name '*.svg' | wc -l)" -eq 8
git status --short --branch
```

- [ ] **Step 2: Confirm delivery history**

Verify every LH60 implementation commit is present on `origin/lh60-rp2040-v2` and the current worktree is clean.
