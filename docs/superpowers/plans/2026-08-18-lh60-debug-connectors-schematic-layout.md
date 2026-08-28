# LH60 Debug Connectors and Schematic Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `TP1..TP23` with six grouped 2.54 mm headers, rebuild the schematic as a readable A3 single page with the approved field visibility, and synchronize/place the headers on the PCB back side without routing them.

**Architecture:** Pure Python contracts own connector geometry, pin maps, schematic coordinates, field display, and eventual PCB placement. Every KiCad library, schematic, project-table, and PCB mutation flows through Konnect: first on disposable candidates, then on production only after candidate checks pass; production PCB writes are serialized behind schematic completion and the exact `update_pcb_from_schematic` revision gate.

**Tech Stack:** Python 3 `unittest`, Konnect MCP 0.6.1 feature build, KiCad 10 CLI exports/ERC/DRC, project-local KiCad libraries.

## Global Constraints

- Approved design: `docs/superpowers/specs/2026-08-18-lh60-debug-connectors-schematic-layout-design.md`.
- Requirement integration branch: existing `task/debug-connectors-layout`; integration worktree: `/data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-layout/lh60`.
- Root `/data00/home/wangqiyilang/playground/lh60` stays clean on `master`.
- Never directly edit or extend text parsing of `*.kicad_pro`, `*.kicad_sch`, `*.kicad_pcb`, `*.kicad_sym`, `*.kicad_mod`, `sym-lib-table`, or `fp-lib-table`.
- Library and production KiCad writes use Konnect only. Read production state through Konnect queries or exported netlist/SVG/PnP/DRC artifacts.
- Matrix remains 10×7 `COL2ROW`: `COL0..COL9 = GP0..GP9`, `ROW0..ROW6 = GP10..GP15,GP26`; `GP27..GP29` remain auxiliary.
- Preserve 75 switches, 70 diodes, their references, values, footprints, logical nodes, and pin mapping. `SW59` remains retired.
- Six connector pin maps are literal reviewed data; do not derive them from a flat net order.
- Signal headers contain no duplicate GND; `J1.3` is common GND.
- Header library artwork is canonical `F.*`; each placed `J1..J6` instance is flipped exactly once to `B.Cu`.
- The scope places but does not route connectors. Expected connector ratsnest is not a DRC waiver for shorts, clearance, edge, hole, or courtyard errors.
- Production schematic and PCB tasks are serial; no two agents may write either file concurrently.
- The deployed Konnect gate must expose `batch_set_schematic_field_visibility`, `create_symbol.reference_at/value_at`, `flip_component`, and `update_pcb_from_schematic` before production writes.
- Run KiCad AppImage CLI commands serially or with a unique `TMPDIR` to avoid extraction races.
- Each logical unit is tested, committed, and pushed before the next unit. Every commit ends with exactly one `Co-authored-by: TRAE CLI <noreply@bytedance.com>`; use a temporary empty `core.hooksPath` because the configured attribution hook appends a different trailer.

## Frozen Connector Interface

| Ref | Value | Symbol / footprint size | Pin map |
|---|---|---:|---|
| `J1` | `PWR` | 1×3 | `1=VSYS, 2=3V3, 3=GND` |
| `J2` | `COL_A` | 1×5 | `1=COL0, 2=COL1, 3=COL2, 4=COL3, 5=COL4` |
| `J3` | `COL_B` | 1×5 | `1=COL5, 2=COL6, 3=COL7, 4=COL8, 5=COL9` |
| `J4` | `ROW_A` | 1×4 | `1=ROW0, 2=ROW1, 3=ROW2, 4=ROW3` |
| `J5` | `ROW_B` | 1×3 | `1=ROW4, 2=ROW5, 3=ROW6` |
| `J6` | `AUX` | 1×3 | `1=GP27, 2=GP28, 3=GP29` |

## Frozen Schematic Layout

All coordinates are multiples of 1.27 mm:

```python
PAGE_SIZE = "A3"
PAGE_PORTRAIT = False
MATRIX_X0_MM = 20.32
MATRIX_Y0_MM = 20.32
MATRIX_X_PITCH_MM = 30.48
MATRIX_Y_PITCH_MM = 33.02
SWITCH_Y_OFFSETS_MM = (10.16, 17.78)
MCU_POSITION_MM = (350.52, 45.72)
CONNECTOR_POSITIONS_MM = {
    "J1": (330.20, 96.52),
    "J2": (330.20, 134.62),
    "J3": (330.20, 177.80),
    "J4": (373.38, 134.62),
    "J5": (373.38, 175.26),
    "J6": (373.38, 215.90),
}
POWER_FLAG_POSITIONS_MM = {
    "#FLG01": (381.00, 86.36),
    "#FLG02": (381.00, 96.52),
    "#FLG03": (381.00, 106.68),
}
```

The RP2040-Tiny library symbol uses `reference_at=(0,17.78,0)` and `value_at=(0,-25.40,0)`. This puts its visible Value more than 5 mm clear of the symbol body and bottom pin-label band; the candidate SVG is still the final visual gate.

## File Map

| File | Responsibility |
|---|---|
| `tools/lh60_design/mcp.py` | Parsed JSON result helper for query-based acceptance |
| `tools/verify_core_library.py` | Core-library unit contract split from schematic tests |
| `tools/lh60_design/core_library.py` | Connector symbol and THT footprint specs/operations |
| `tools/verify_connector_library.py` | Connector spec and FakeClient operation tests |
| `tools/check_connector_library_acceptance.py` | Konnect-query acceptance for generated connector assets and project registration |
| `lib/lh60-core/README.md` | Provenance and front-library/back-instance semantics |
| `tools/lh60_design/schematic.py` | Page, connector map, coordinates, visibility, candidate/production convergence |
| `tools/verify_schematic_contract.py` | Pure schematic inventory/connectivity contract |
| `tools/verify_schematic_apply.py` | FakeClient apply ordering and capability gates |
| `tools/lh60_design/mcu_library.py` | RP2040-Tiny explicit field anchors |
| `tools/verify_lh60.py` | MCU payload contract |
| `tools/check_schematic_acceptance.py` | Live Konnect/export acceptance; not source parsing |
| `tools/lh60_design/pcb.py` | Connector placement model and final-state apply |
| `tools/verify_pcb_placement.py` | Pure placement geometry and FakeClient calls |
| `tools/check_pcb_acceptance.py` | Live board queries/DRC/SVG/PnP acceptance |
| `docs/reports/2026-08-18-debug-connectors-baseline.json` | Pre-delete TP positions, functional centroids, component inventory, and DRC baseline |
| `docs/reports/2026-08-18-debug-connectors-placement.md` | Frozen placements and physical extraction-volume record |

## Units, Worktrees, and Dependencies

```text
L0 test/query seams
├── L1 connector library ─┐
├── L2 schematic plan ────┼── true blockers ──> L4 production schematic
└── L3 MCU field anchors ─┘                         |
Konnect field-display deployment ───────────────────┘
                                                    |
                                                    v
                                      L5 live PCB synchronization
                                                    |
                                                    v
                                      L6 placement + acceptance
```

- L1, L2, and L3 may run in parallel after L0 because their file scopes are disjoint.
- L4 truly depends on all three source contracts and the deployed Konnect schema.
- L5 truly depends on the completed saved schematic and a live KiCad PCB editor.
- L6 truly depends on the synchronized footprints and must run with the board closed for `flip_component`, then reopened for final inspection.

---

### Task L0: Split Test Ownership and Add Query Result Parsing

**Files:**
- Modify: `tools/lh60_design/mcp.py`
- Modify: `tools/verify_schematic_contract.py`
- Create: `tools/verify_core_library.py`

**Interfaces:**
- Consumes: current 59-test baseline.
- Produces: `McpClient.call_tool_json(name, arguments) -> dict` and disjoint L1/L2 test files.

- [ ] **Step 0: Create the isolated L0 worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/debug-connectors-test-seams \
  /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-test-seams/lh60 \
  task/debug-connectors-layout
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-test-seams/lh60
```

- [ ] **Step 1: Add RED tests for JSON result parsing**

At the bottom of the newly created `tools/verify_core_library.py`, add `McpClientResultTest` and use a fabricated result:

```python
result = {"content": [{"type": "text", "text": '{"count": 6}'}]}
self.assertEqual(McpClient.result_json(result), {"count": 6})
```

Also assert missing text, invalid JSON, and `isError=true` raise `RuntimeError`.

- [ ] **Step 2: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_core_library
```

Expected: fail because `result_json` does not exist.

- [ ] **Step 3: Move only `CoreLibraryContractTest` and implement the helper**

Move the class, then split its mixed responsibilities: retain existing source-parser assertions only for the already-established diode/test-point regression, move all new connector assertions to pure Python specs or `check_connector_library_acceptance.py`, and do not add connector names to `test_generated_library_is_parseable_and_registered_portably`. Add:

```python
@staticmethod
def result_json(result: dict[str, object]) -> dict[str, object]:
    if result.get("isError"):
        raise RuntimeError(result)
    for block in result.get("content", []):
        if block.get("type") == "text":
            value = json.loads(block["text"])
            if isinstance(value, dict):
                return value
    raise RuntimeError("tool result has no JSON object text block")

def call_tool_json(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return self.result_json(self.call_tool(name, arguments))
```

- [ ] **Step 4: Prove no behavioral change**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m compileall -q tools
git diff --check
```

Expected: 59 tests plus the new helper tests pass.

- [ ] **Step 5: Commit and push L0**

```bash
git add tools/lh60_design/mcp.py tools/verify_schematic_contract.py \
  tools/verify_core_library.py
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "test: split schematic and core library contracts" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/debug-connectors-test-seams
```

- [ ] **Step 6: Integrate L0 before dispatching L1-L3**

```bash
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-layout/lh60
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-test-seams/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
git push origin task/debug-connectors-layout
```

---

### Task L1: Project-Local Connector Symbols and Footprints

**Files:**
- Modify: `tools/lh60_design/core_library.py`
- Modify: `tools/verify_core_library.py`
- Create: `tools/verify_connector_library.py`
- Create: `tools/check_connector_library_acceptance.py`
- Modify: `lib/lh60-core/README.md`
- Modify through Konnect only: `lib/lh60-core/lh60-core.kicad_sym`
- Create through Konnect only: three `lib/lh60-core/lh60-core.pretty/PinHeader_*.kicad_mod` files

**Interfaces:**
- Consumes: Konnect `create_symbol`, `create_footprint`, `set_footprint_graphics`, `set_footprint_metadata`, registration/query tools.
- Produces: `lh60-core:Conn_01x03/04/05` and canonical-front `lh60-core:PinHeader_1x03/04/05_P2.54mm_Vertical`.

- [ ] **Step 1: Create isolated worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/debug-connectors-library \
  /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-library/lh60 \
  task/debug-connectors-layout
```

- [ ] **Step 2: Write RED connector spec tests**

Test exact names, pin counts, sequential passive pins, THT types, pad coordinates, 1.00 mm drill, 1.70 mm size, `*.Cu/*.Mask`, pad-1 shape, body/courtyard formula, `F.*`-only graphics, and attributes exactly `("exclude_from_pos_files",)`.

Use these assertions:

```python
self.assertEqual([s.name for s in connector_symbols()],
                 ["Conn_01x03", "Conn_01x04", "Conn_01x05"])
self.assertEqual([(p.number, p.x, p.y) for p in header.pads],
                 [(str(i), 0.0, (i - 1) * 2.54) for i in range(1, n + 1)])
self.assertEqual(header.body_width_mm, 2.54)
self.assertEqual(header.body_height_mm, n * 2.54)
self.assertEqual(header.courtyard_clearance_mm, 0.50)
```

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_connector_library tools.verify_core_library
```

- [ ] **Step 4: Extend the pad/spec model**

Make pad type and drill data-owned, not hard-coded:

```python
@dataclass(frozen=True)
class CorePadSpec:
    number: str
    pad_type: str
    shape: str
    x: float
    y: float
    width: float
    height: float
    layers: tuple[str, ...]
    drill_mm: float | None = None
    roundrect_rratio: float | None = None
```

Update existing diode/test-point specs to preserve their current output. Emit optional `drill` and `roundrect_rratio` only when present.

- [ ] **Step 5: Implement exact connector symbols and footprints**

Pins are on the left, 2.54 mm apart, passive, and numbered 1..N. Header pad 1 is `rect`; the rest are `circle`. Generate:

```python
CorePadSpec(str(pin), "thru_hole", "rect" if pin == 1 else "circle",
            0.0, (pin - 1) * 2.54, 1.70, 1.70,
            ("*.Cu", "*.Mask"), drill_mm=1.00)
```

`_apply_header_graphics` must replace `F.Fab`, `F.CrtYd`, and `F.SilkS` with the approved line widths and pin-1 marker; it must never write `B.*` library graphics.

- [ ] **Step 6: Run GREEN, then generate assets through Konnect**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_connector_library tools.verify_core_library
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.core_library --apply
```

Then run `tools/check_connector_library_acceptance.py`. It queries each symbol with `get_symbol_info`, each footprint with `get_footprint_info(include_graphics=true)`, and the project registrations with `list_symbol_libraries`/`list_footprint_libraries`. Assert returned geometry, metadata, and portable project registration; do not parse source files or library tables in new tests. Remove connector coverage from any source-text parsing assertion rather than extending that parser.

- [ ] **Step 7: Document provenance and assembly semantics**

Record the KiCad generic connector contract, project-local IDs, sequential pin numbering, canonical-front library artwork, production `B.Cu` flip, PnP exclusion, and BOM inclusion in `lib/lh60-core/README.md`.

- [ ] **Step 8: Run focused checks, commit, and push**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_connector_library tools.verify_core_library
PYTHONDONTWRITEBYTECODE=1 python tools/check_connector_library_acceptance.py
PYTHONDONTWRITEBYTECODE=1 python -m compileall -q tools
git diff --check
git add tools/lh60_design/core_library.py tools/verify_core_library.py \
  tools/verify_connector_library.py tools/check_connector_library_acceptance.py \
  lib/lh60-core
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(lib): add grouped debug pin headers" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/debug-connectors-library
```

---

### Task L2: Deterministic A3 Schematic Plan

**Files:**
- Modify: `tools/lh60_design/schematic.py`
- Modify: `tools/verify_schematic_contract.py`
- Create: `tools/verify_schematic_apply.py`

**Interfaces:**
- Consumes: frozen connector IDs/pin maps and Konnect field-visibility schema.
- Produces: `SchematicPlan(components, connections, page_size, portrait, field_visibility)` with 155 components and 339 pin assignments.

- [ ] **Step 1: Create isolated worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/debug-connectors-schematic-plan \
  /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-schematic-plan/lh60 \
  task/debug-connectors-layout
```

- [ ] **Step 2: Write RED inventory, map, page, grid, and visibility tests**

Define expected connector maps literally. Assert:

```python
self.assertEqual(len(plan.components), 155)
self.assertEqual(len(plan.connections), 339)
self.assertFalse(any(c.reference.startswith("TP") for c in plan.components))
self.assertEqual((plan.page_size, plan.portrait), ("A3", False))
self.assertEqual(field_state("D1"), (False, False))
self.assertEqual(field_state("SW1"), (False, True))
self.assertEqual(field_state("J1"), (True, True))
self.assertEqual(field_state("U1"), (True, True))
```

Assert all component coordinates divide by 1.27 within 1e-9; matrix X/Y pitch equals the frozen constants; the longest 26-character switch Value has at least the 30.48 mm column band and each row has room for two switch offsets.

- [ ] **Step 3: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_schematic_contract.SchematicPlanContractTest \
  tools.verify_schematic_apply
```

- [ ] **Step 4: Implement explicit connector and display types**

```python
@dataclass(frozen=True)
class ConnectorGroup:
    reference: str
    value: str
    lib_id: str
    footprint: str
    pin_map: tuple[tuple[str, str], ...]
    x: float
    y: float

@dataclass(frozen=True)
class FieldVisibility:
    reference: str
    reference_visible: bool
    value_visible: bool
```

Add `page_size`, `portrait`, and `field_visibility` to `SchematicPlan`. Replace `test_point_nets` and `_test_point_connections` with literal `connector_groups` and connector pin connections. Preserve three power flags.

- [ ] **Step 5: Freeze the approved layout constants**

Use the constants listed in this plan verbatim. For each logical node:

```python
x = MATRIX_X0_MM + node.column * MATRIX_X_PITCH_MM
y = MATRIX_Y0_MM + node.row * MATRIX_Y_PITCH_MM
diode_y = y
switch_y = y + SWITCH_Y_OFFSETS_MM[socket_index]
```

Reject more switches than available offsets rather than silently overlapping them.

- [ ] **Step 6: Define apply-call ordering with a FakeClient**

`verify_schematic_apply.py` must assert that a blank target calls `set_schematic_page`, one `batch_place_components`, one `batch_edit_schematic_components`, grouped `batch_connect_to_net` calls, one `batch_set_schematic_field_visibility`, then `update_symbols_from_library(allow_pin_moves=False)`. The expected visibility payload enumerates all 70 diodes, all 75 active switches, six connectors, and U1.

- [ ] **Step 7: Run GREEN, commit, and push**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_schematic_contract.SchematicPlanContractTest \
  tools.verify_schematic_apply
git diff --check
git add tools/lh60_design/schematic.py tools/verify_schematic_contract.py \
  tools/verify_schematic_apply.py
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(schematic): define grouped connector layout" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/debug-connectors-schematic-plan
```

---

### Task L3: RP2040-Tiny Field Anchors

**Files:**
- Modify: `tools/lh60_design/mcu_library.py`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- Consumes: Konnect `create_symbol.reference_at/value_at` frozen in the companion plan.
- Produces: U1 library Reference at `(0,17.78,0)` and Value at `(0,-25.40,0)`.

- [ ] **Step 1: Create isolated worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/rp2040-field-anchors \
  /data00/home/wangqiyilang/playground/lh60/.worktree/rp2040-field-anchors/lh60 \
  task/debug-connectors-layout
```

- [ ] **Step 2: Add RED payload assertions**

```python
payload = symbol_payload()
self.assertEqual(payload["reference_at"], {"x": 0.0, "y": 17.78, "rotation": 0.0})
self.assertEqual(payload["value_at"], {"x": 0.0, "y": -25.40, "rotation": 0.0})
```

Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_lh60.Rp2040TinyContractTest` and confirm RED.

- [ ] **Step 3: Add the two payload objects without changing pins or footprint**

Only `symbol_payload()` changes. Do not regenerate the protected library until the deployed Konnect schema gate passes.

- [ ] **Step 4: Run GREEN, commit, and push**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_lh60.Rp2040TinyContractTest
git diff --check
git add tools/lh60_design/mcu_library.py tools/verify_lh60.py
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "fix(lib): separate RP2040 schematic fields" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/rp2040-field-anchors
```

---

### Task L4: Integrate Source Contracts and Rebuild the Production Schematic

**Files:**
- Modify: `tools/lh60_design/schematic.py` apply/convergence path
- Create: `tools/check_schematic_acceptance.py`
- Modify through Konnect only: `lib/lh60-mcu/lh60-mcu.kicad_sym`
- Modify through Konnect only: `lh60.kicad_sch`

**Interfaces:**
- Consumes: L1/L2/L3 branch heads and deployed Konnect field-display schemas.
- Produces: saved A3 production schematic with 155 components, 0 wire segments, 339 pin-end labels, approved field visibility, and ERC 0/0.

- [ ] **Step 1: Integrate L1, L2, and L3 one commit at a time**

From the integration worktree:

```bash
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-layout/lh60
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-library/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_connector_library tools.verify_core_library
git push origin task/debug-connectors-layout

git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-schematic-plan/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_schematic_contract.SchematicPlanContractTest \
  tools.verify_schematic_apply
git push origin task/debug-connectors-layout

git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/rp2040-field-anchors/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_lh60.Rp2040TinyContractTest
git push origin task/debug-connectors-layout
```

Expected: each checkpoint is independently green and pushed before the next cherry-pick.

- [ ] **Step 1a: Create the isolated L4 production-schematic worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/debug-connectors-production-schematic \
  /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-production-schematic/lh60 \
  task/debug-connectors-layout
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-production-schematic/lh60
```

- [ ] **Step 2: Enforce the deployed capability gate before any protected write**

Add a helper and test it with FakeClient schemas:

```python
def require_schematic_capabilities(client: McpClient) -> None:
    batch = client.tool_schemas("sch_batch")
    components = client.tool_schemas("sch_components")
    library = client.tool_schemas("library")
    required_batch = {
        "batch_place_components",
        "batch_edit_schematic_components",
        "batch_connect_to_net",
        "batch_set_schematic_field_visibility",
    }
    missing = required_batch - batch.keys()
    if missing:
        raise RuntimeError(f"missing Konnect schematic tools: {sorted(missing)}")
    for field in ("reference_at", "value_at"):
        if field not in library["create_symbol"]["properties"]:
            raise RuntimeError(f"create_symbol missing {field}")
    assert "set_schematic_page" in components
```

Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_schematic_apply`. Expected: pass only with correct FakeClient contracts.

- [ ] **Step 3: Regenerate project-local libraries through the deployed Konnect**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.core_library --apply
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.mcu_library --apply
```

Use `get_symbol_info` and `get_footprint_info(include_graphics=true)` to prove connectors and U1 resolve. Do not inspect source library files directly for new acceptance.

- [ ] **Step 4: Create and validate a disposable candidate project**

Create a unique temporary directory, then use Konnect `create_project` and project-scope registration tools. Call the same `apply_schematic(client, candidate_schematic)` used for production. Do not copy a protected production file.

```bash
candidate_dir=$(mktemp -d /tmp/lh60-debug-sch.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.schematic \
  --schematic "$candidate_dir/lh60-debug.kicad_sch" \
  --project-dir "$candidate_dir" --create-candidate --apply
```

The candidate must report exactly 155 components, 0 wires, and 339 labels through Konnect `get_schematic_layout`; `batch_connect_to_net` places labels directly on pin endpoints and does not create stubs.

- [ ] **Step 5: Run candidate structural and electrical gates**

Through Konnect, run in order:

```text
list_schematic_components
export_netlist_summary
get_schematic_layout
check_schematic_overlaps
find_orphan_items
find_shorted_nets
find_single_pin_nets
validate_wire_connections
validate_component_connections
run_erc
export_schematic_svg
```

Acceptance:

```text
component inventory 1 MCU + 75 switches + 70 diodes + 6 connectors + 3 flags
no TP reference or TestPoint footprint
23 exported debug nets, each on one connector pin
no shorted nets
no unexpected orphan/single-pin/wire/component findings
ERC: 0 errors, 0 warnings
A3 landscape SVG: no overlap, no title-block intrusion
U1 Value has >=5 mm clear space from body/pin-label band
every visible switch Value is distinct
J1..J6 Reference, Value, and pin labels occupy separate readable bands
```

If the SVG fails, adjust only the pure coordinate/anchor contract, update its tests, commit/push that corrective unit, and rebuild the candidate. Never patch the candidate or production S-expression.

- [ ] **Step 6: Implement a production convergence preflight**

`check_schematic_acceptance.py --preflight` queries production via Konnect and requires this exact known baseline before deletion:

```python
assert layout["component_count"] == 172
assert layout["wire_count"] == 290
assert layout["label_count"] == 339
assert set(tp_refs) == {f"TP{i}" for i in range(1, 24)}
```

It must also confirm the candidate acceptance JSON was produced by the current plan hash. Any mismatch stops before mutation.

- [ ] **Step 7: Rebuild production exclusively through Konnect**

Use a single scripted convergence sequence:

1. `list_schematic_wires` and the upgraded `list_schematic_labels` obtain exact UUIDs for all current wires and labels.
2. `batch_delete_schematic_wire` deletes all 290 wire UUIDs in one call; this prunes orphaned junctions.
3. `batch_delete(uuids=[...])` deletes all 339 label UUIDs in one atomic call. Refuse an empty/missing UUID before the call; duplicate same-net/same-position labels remain safe because identity is UUID-based.
4. `batch_delete_schematic_components` deletes all 172 references, including `TP1..TP23`.
5. Assert layout counts are 0 components, 0 wires, 0 labels.
6. Apply the complete reviewed plan: A3 page, 155 components, fields, 339 pin-end labels, visibility, symbol refresh.

Do not call `move_connected`: current Konnect delegates it to a plain symbol move and does not move wires or labels.

- [ ] **Step 8: Re-run every candidate gate on production**

Run `tools/check_schematic_acceptance.py --production --output /tmp/lh60-debug-sch-acceptance.json`. Require the same inventory, net, structural, ERC, and SVG gates as Step 5. Run the convergence a second time on a disposable candidate and prove its semantic query outputs are identical; production itself is not rewritten a second time.

- [ ] **Step 9: Run the repository suite and commit the L4 code/library unit**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m compileall -q tools
git diff --check
git diff --name-only -- lh60.kicad_pcb
```

Expected: all tests pass; PCB diff is empty.

```bash
git add tools/lh60_design/schematic.py tools/check_schematic_acceptance.py \
  lib/lh60-core lib/lh60-mcu
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(schematic): add A3 convergence checks" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/debug-connectors-production-schematic
```

- [ ] **Step 10: Commit the independently revertible production schematic**

```bash
git add lh60.kicad_sch
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "refactor(schematic): group debug headers on A3" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push origin task/debug-connectors-production-schematic
```

- [ ] **Step 11: Integrate both L4 commits one at a time**

```bash
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-layout/lh60
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-production-schematic/lh60 rev-parse HEAD~1)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_schematic_apply
git push origin task/debug-connectors-layout
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-production-schematic/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python tools/check_schematic_acceptance.py --production
git push origin task/debug-connectors-layout
```

---

### Task L5: Live Test-Pad Removal and Schematic-to-PCB Synchronization

**Files:**
- Create: `tools/sync_debug_connectors.py`
- Create: `tools/verify_pcb_sync.py`
- Create: `docs/reports/2026-08-18-debug-connectors-baseline.json`
- Modify through Konnect only: `lh60.kicad_pcb`

**Interfaces:**
- Consumes: accepted production schematic and Konnect `update_pcb_from_schematic`.
- Produces: board with `TP1..TP23` explicitly removed through live IPC and `J1..J6` added at staged front-side positions, preserving all unrelated board state.

- [ ] **Step 0: Create the isolated L5 PCB-sync worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/debug-connectors-pcb-sync \
  /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-sync/lh60 \
  task/debug-connectors-layout
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-sync/lh60
```

- [ ] **Step 1: Write FakeClient RED tests for the exact revision gate**

Create `tools/verify_pcb_sync.py`. Assert the script first verifies and deletes exactly `TP1..TP23` through `delete_component` while the target board is live over IPC. Only then may it dry-run sync. Assert apply receives the exact returned `plan_revision`, non-ready/conflict diagnostics abort, and changes are rejected unless they add exactly six J footprints with 23 expected pad nets and contain no unrelated update/pad reassignment. Assert `coverage.board_only_preserved.planned` equals the baseline component-list count minus the 23 TP footprints and all matched schematic footprints; separately query `get_component_list` after deletion and reject any remaining `TP*`, because the sync response exposes only a count, not preserved references.

- [ ] **Step 2: Run RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync
```

- [ ] **Step 3: Implement strict sync review**

```python
def sync_debug_connectors(client, schematic: Path, board: Path) -> dict:
    refs = component_references(client, board)
    expected_tp = {f"TP{i}" for i in range(1, 24)}
    if expected_tp - refs:
        raise RuntimeError("production board is missing expected TP baseline")
    preview = client.call_tool_json("update_pcb_from_schematic", {
        "schematic": str(schematic), "board": str(board), "dry_run": True,
    })
    assert_preview_before_tp_removal(preview)
    for reference in sorted(expected_tp, key=lambda value: int(value[2:])):
        client.call_tool_json("delete_component", {
            "board": str(board), "reference": reference,
        })
    dry = client.call_tool_json("update_pcb_from_schematic", {
        "schematic": str(schematic), "board": str(board), "dry_run": True,
    })
    assert_expected_debug_only_plan(dry)
    return client.call_tool_json("update_pcb_from_schematic", {
        "schematic": str(schematic), "board": str(board),
        "dry_run": False,
        "expected_plan_revision": dry["plan_revision"],
    })
```

- [ ] **Step 4: Run GREEN and focused tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync
```

- [ ] **Step 5: Start the live KiCad gate**

Close the schematic editor. Start Xvfb when no display is available, launch the PCB editor with this worktree's `lh60.kicad_pcb`, enable IPC, and confirm `open_project` reports the exact project/board path. No other agent may use PCB IPC. Before any delete, query and write `docs/reports/2026-08-18-debug-connectors-baseline.json` with all component references/positions/layers, each TP pad/net/position, the six functional-group centroids derived from the frozen pin map, full DRC findings, and the current commit SHA. Commit and push this report together with L5.

- [ ] **Step 6: Execute dry run, inspect, then apply exact revision**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m tools.sync_debug_connectors --apply \
  --report /tmp/lh60-debug-pcb-sync.json
```

The script first performs a dry run while TP footprints still exist and requires only six J additions plus the expected board-only-preserved TP baseline. It then performs the copper checks, deletes TP, performs a second dry run, and only then applies the second run's exact revision. Require six additions, no unrelated update/pad reassignment, no preserved `TP*`, and explicit preservation of all remaining board-only/routed state. Before deleting, require `get_board_info.zone_count == 0`. For every TP call `get_component_pads`, then call `query_traces` with `net_name=pad["net"]`; reject deletion if any returned segment/via endpoint lies inside the 1.5 mm test-pad diameter (plus design-rule clearance) around that TP pad. If any zone exists or copper safety cannot be proved, stop for manual review. On any post-delete failure, do not call `save_project`: close KiCad without saving and discard/recreate the isolated L5 worktree from the clean integration branch.

- [ ] **Step 7: Save and query the board**

Call `save_project`, then `get_component_list` and `get_component_pads`. Require no `TP*`; `J1..J6` exist; their 23 pad nets match the frozen map.

- [ ] **Step 8: Commit and push the L5 tool/baseline unit**

```bash
git add tools/sync_debug_connectors.py tools/verify_pcb_sync.py \
  docs/reports/2026-08-18-debug-connectors-baseline.json
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(pcb): add guarded debug-header synchronization" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/debug-connectors-pcb-sync
```

- [ ] **Step 9: Commit the independently revertible synchronized PCB**

```bash
git add lh60.kicad_pcb
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "refactor(pcb): replace test pads with debug headers" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push origin task/debug-connectors-pcb-sync
```

- [ ] **Step 10: Integrate both L5 commits and verify six unsited footprints**

```bash
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-layout/lh60
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-sync/lh60 rev-parse HEAD~1)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync
git push origin task/debug-connectors-layout
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-sync/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync
git push origin task/debug-connectors-layout
```

---

### Task L6: Deterministic Back-Side Placement and Acceptance

**Files:**
- Modify: `tools/lh60_design/pcb.py`
- Modify: `tools/verify_pcb_placement.py`
- Create: `tools/check_pcb_acceptance.py`
- Create: `docs/reports/2026-08-18-debug-connectors-placement.md`
- Modify through Konnect only: `lh60.kicad_pcb`

**Interfaces:**
- Consumes: synchronized `J1..J6` and deployed `move_component`, `rotate_component`, final-state `flip_component(layer="B.Cu")`, queries/DRC/exports.
- Produces: frozen collision-free placement plan, bottom-side headers, report, and no connector-related geometry violations.

- [ ] **Step 0: Create the isolated L6 placement worktree**

```bash
git -C /data00/home/wangqiyilang/playground/lh60 worktree add \
  -b task/debug-connectors-pcb-placement \
  /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-placement/lh60 \
  task/debug-connectors-layout
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-placement/lh60
```

- [ ] **Step 1: Keep new acceptance independent of production-source parsing**

Do not extend or modify `read_board_placements`. New `ConnectorPlacement` tests use pure geometry and FakeClient responses; live acceptance uses `get_component_list`, `get_component_pads`, and graphics queries. Keep the legacy socket tests byte-for-byte unchanged in this task.

- [ ] **Step 2: Add RED placement geometry tests**

```python
@dataclass(frozen=True)
class ConnectorPlacement:
    reference: str
    pin_count: int
    x_mm: float
    y_mm: float
    rotation_deg: float
    layer: str = "B.Cu"
    extraction_clearance_mm: float = 15.0

    def access_envelope(self) -> Rect:
        body_length = self.pin_count * 2.54
        # rotate the 2.54 x body_length housing, then add 1.00 mm per side
```

Assert six unique references, 0.5 mm grid, inside 285.75×95.25 mm board, non-overlapping access envelopes, pin-1 orientation recorded, and 15 mm extraction clearance.

- [ ] **Step 3: Implement deterministic candidate generation and freeze rule**

Before coordinates are known, `candidate_connector_placements()` reads the committed L5 baseline JSON and uses each connector group's recorded legacy-TP centroid. Freeze this bounded offset list and enumerate in reference order, offset-list order, then rotation `0, 90, 180, 270`:

```python
CANDIDATE_OFFSETS_MM = (
    (0.0, 0.0),
    (-5.0, 0.0), (5.0, 0.0), (0.0, -5.0), (0.0, 5.0),
    (-5.0, -5.0), (5.0, -5.0), (-5.0, 5.0), (5.0, 5.0),
    (-10.0, 0.0), (10.0, 0.0), (0.0, -10.0), (0.0, 10.0),
    (-10.0, -10.0), (10.0, -10.0), (-10.0, 10.0), (10.0, 10.0),
)
```

This caps the first-pass search at `6 * 17 * 4 = 408` candidates. If no solution exists, stop and report the rejected-candidate table; expanding the search region is a design change, not an implicit fallback. For each candidate:

1. reject board-edge/access-envelope violations in pure Python;
2. create a disposable board with Konnect by syncing the accepted schematic into a temporary project, then apply the current production footprint placements through existing placement APIs; do not copy `lh60.kicad_pcb`;
3. cache every existing back-side courtyard via `list_board_footprint_graphics(reference, layer="B.CrtYd")`; reject a candidate if its Dupont access envelope intersects any returned outline or another accepted connector envelope;
4. place/move the candidate through Konnect and use `check_clearance(board,Jx,ref)` only to order nearest footprint origins for diagnostics; it is not a courtyard measurement;
5. reject any new non-unconnected DRC/courtyard finding on the disposable board; normalize DRC entries as `(test_id, severity, sorted_refs, layer, message)` and require the candidate set minus the committed baseline set to contain only the expected J ratsnest entries;
6. select the first passing candidate and continue to the next reference.

Once all six pass, write those exact coordinates as `FROZEN_CONNECTOR_PLACEMENTS` in `pcb.py` in the same commit as the report. Subsequent runs consume the frozen tuple and never search again unless the board baseline changes and tests intentionally fail.

- [ ] **Step 4: Add FakeClient apply ordering tests**

For each frozen placement, require:

```text
move_component(reference,x,y)
rotate_component(reference,rotation)
get_component_list -> inspect current layer
flip_component(reference,layer="B.Cu") only when not already B.Cu
get_component_list -> assert B.Cu
```

Reject a schema without `flip_component`. Reapplying to FakeClient state already on B.Cu must not flip back.

- [ ] **Step 5: Run RED then GREEN for the pure plan**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_pcb_placement.ConnectorPlacementPlanTest
```

Expected first RED before implementation, then GREEN after the frozen plan and calls exist.

- [ ] **Step 6: Close the live board and apply final-side placement safely**

Save and close the PCB editor because deployed `flip_component` is a revision-checked closed-board operation. Run `apply_connector_placements`; `move_component` and `rotate_component` use safe closed-board fallbacks, and `flip_component(layer="B.Cu")` establishes final state. Reopen the exact board afterward and save once through KiCad.

- [ ] **Step 7: Query placed pads and graphics**

Through Konnect require:

```text
J1..J6 all layer B.Cu
23 pads on exact reviewed nets
placed graphics on B.Fab, B.CrtYd, B.SilkS
no connector artwork on F.Fab, F.CrtYd, F.SilkS
pin-1 marker and Reference present/readable from back assembly view
```

- [ ] **Step 8: Run DRC, back-layer SVG, and PnP gates**

Run `run_drc(severity="info", limit large enough for full baseline)` and compare against a pre-placement baseline report. Accept only the 23 expected connector unrouted endpoints; reject new connector short, clearance, hole, edge, courtyard, missing-net, or unexpected unconnected findings.

Export:

```text
B.SilkS,B.Fab,B.CrtYd,Edge.Cuts -> /tmp/lh60-debug-back.svg
position CSV side=both -> /tmp/lh60-debug-pos.csv
```

Visually inspect the SVG from the back assembly view. Parse only the exported CSV and assert none of `J1..J6` appears.

- [ ] **Step 9: Write the placement report**

Record each reference, pins, X/Y, rotation, B.Cu, access envelope, nearest measured clearance, pin-1 direction, and 15 mm extraction volume. Include DRC baseline/delta, PnP exclusion, SVG path/hash, and the Konnect integration SHA used.

- [ ] **Step 10: Run all fresh verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python -m compileall -q tools
PYTHONDONTWRITEBYTECODE=1 python tools/check_schematic_acceptance.py --production
PYTHONDONTWRITEBYTECODE=1 python tools/check_pcb_acceptance.py --production
git diff --check
```

Expected: software suite green, schematic ERC 0/0, connector acceptance clean except exactly documented ratsnest.

- [ ] **Step 11: Commit and push the L6 placement tool/report unit**

```bash
git add tools/lh60_design/pcb.py tools/verify_pcb_placement.py \
  tools/check_pcb_acceptance.py \
  docs/reports/2026-08-18-debug-connectors-placement.md
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(pcb): freeze grouped header placement" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/debug-connectors-pcb-placement
```

- [ ] **Step 12: Commit the independently revertible placed PCB**

```bash
git add lh60.kicad_pcb
empty_hooks=$(mktemp -d /tmp/lh60-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(pcb): place grouped debug headers" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push origin task/debug-connectors-pcb-placement
```

- [ ] **Step 13: Integrate both L6 commits and rerun live acceptance**

```bash
cd /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-layout/lh60
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-placement/lh60 rev-parse HEAD~1)"
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_pcb_placement.ConnectorPlacementPlanTest
git push origin task/debug-connectors-layout
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/lh60/.worktree/debug-connectors-pcb-placement/lh60 rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 python tools/check_schematic_acceptance.py --production
PYTHONDONTWRITEBYTECODE=1 python tools/check_pcb_acceptance.py --production
git push origin task/debug-connectors-layout
```

---

### Task L7: Final Integration Review and Handoff

**Files:** No new source file required; update the placement report only if fresh evidence changes.

**Interfaces:**
- Consumes: full L0-L6 commit sequence.
- Produces: reviewed task branch ready for integration into `lh60-rp2040-v2`.

- [ ] **Step 1: Review the whole branch against the approved specification**

Run a two-axis code/design review from `546578c878c0efc53ca0e9ac3eb5e4ebac924e4f`. Confirm every change belongs to the specification and each commit is independently revertible.

- [ ] **Step 2: Re-run the full gates from a clean process**

Restart Konnect to eliminate stale executables. Run the full Python suite, schematic acceptance, PCB acceptance, ERC, DRC delta, SVG, and PnP export again. Record fresh hashes/evidence in the report if different.

- [ ] **Step 3: Push and report the integration sequence**

```bash
git status --short --branch
git log --oneline 546578c878c0efc53ca0e9ac3eb5e4ebac924e4f..HEAD
git push origin task/debug-connectors-layout
```

Return every commit SHA, modified file set, test counts, ERC/DRC findings, schematic SVG, back-layer SVG, PnP proof, Konnect blocking SHA, and exact remaining expected unrouted connector count.
