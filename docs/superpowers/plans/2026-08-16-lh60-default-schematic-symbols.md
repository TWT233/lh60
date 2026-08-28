# LH60 Default Schematic Symbols Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every production switch and matrix diode with KiCad's standard schematic symbols without changing connectivity or PCB placement.

**Architecture:** The Python schematic plan owns the canonical library IDs, and Konnect performs reference-preserving in-place component replacement in the serialized schematic. Existing project-local footprints and the remaining support symbols stay unchanged.

**Tech Stack:** Python `unittest`, Konnect MCP stdio, KiCad 10 `kicad-cli`.

## Global Constraints

- Never edit `*.kicad_sch`, `*.kicad_pcb`, `*.kicad_pro`, `*.kicad_sym`, `*.kicad_mod`, `sym-lib-table`, or `fp-lib-table` as text.
- Switches use `Switch:SW_Push`; diodes use `Device:D`.
- Preserve references, values, footprints, positions, rotations, net labels, and pin mapping.
- Do not modify `lh60.kicad_pcb`.
- End every commit message with `Co-authored-by: TRAE CLI <noreply@bytedance.com>`.

---

### Task 1: Standard Symbol Contract and Production Schematic

**Files:**
- Modify: `tools/verify_schematic_contract.py`
- Modify: `tools/lh60_design/schematic.py`
- Modify: `tools/lh60_design/core_library.py`
- Modify through Konnect only: `lh60.kicad_sch`

**Interfaces:**
- Consumes: `build_schematic_plan() -> SchematicPlan`, Konnect `replace_component(schematic, reference, new_lib_id)`.
- Produces: `CORE_SWITCH = "Switch:SW_Push"` and `CORE_DIODE = "Device:D"`; production instances whose embedded `lib_id` values match those constants.

- [ ] **Step 1: Write the failing contract tests**

Assert that the generated plan uses only `Switch:SW_Push` for switch
components and only `Device:D` for diode components. Assert that the
production schematic embeds those two IDs and no longer embeds
`lh60-core:KeySwitch` or `lh60-core:MatrixDiode`.

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
python -m unittest -v \
  tools.verify_schematic_contract.SchematicPlanContractTest \
  tools.verify_schematic_contract.ProductionSchematicOutputTest
```

Expected: failures showing the current `lh60-core` IDs.

- [ ] **Step 3: Update the source contract**

Set the two constants in `tools/lh60_design/schematic.py` to the approved
standard IDs. Remove only `KeySwitch` and `MatrixDiode` from
`core_symbol_specs()` and update the focused core-library assertions;
`TestPoint` and `PowerFlag` remain project-local.

- [ ] **Step 4: Replace production symbols through Konnect**

Resolve the official KiCad `Device` and `Switch` libraries in the local user
environment. Call `replace_component` for all active `SW*` references with
`Switch:SW_Push` and all `D*` references with `Device:D`. Do not delete and
re-place components.

- [ ] **Step 5: Verify GREEN and electrical integrity**

Run:

```bash
python -m unittest -v \
  tools.verify_schematic_contract.SchematicPlanContractTest \
  tools.verify_schematic_contract.ProductionSchematicOutputTest
kicad-cli sch erc --exit-code-violations --severity-all \
  --output /tmp/lh60-default-symbols-erc.rpt lh60.kicad_sch
```

Expected: all focused tests pass and ERC reports zero errors and warnings.

- [ ] **Step 6: Run complete verification**

Run:

```bash
python -m unittest discover -s tools -p 'verify_*.py' -v
python -m compileall -q tools
git diff --check
git diff --name-only HEAD -- lh60.kicad_pcb
```

Expected: all tests pass, checks exit zero, and the PCB diff is empty.

- [ ] **Step 7: Commit and push**

```bash
git add -A
git commit -m "refactor(schematic): use default switch and diode symbols" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
git push origin lh60-rp2040-v2
```
