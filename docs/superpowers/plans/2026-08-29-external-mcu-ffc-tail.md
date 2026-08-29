# LH60 External MCU FFC Tail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the out-of-bounds on-keyboard RP2040-Tiny and six debug headers with a passive keyboard matrix board, one `C2856805` 24-pin FFC interface, and a separately mounted RP2040-Tiny tail board.

**Architecture:** A frozen pure-Python inter-board contract is the single source of truth for the 24-pin map and GPIO mapping. A project-local `C2856805` library feeds two independently generated schematics. PCB work begins only after a Mechanical Interface Freeze (MIF), then the root keyboard PCB and the new tail PCB proceed in isolated worktrees before physical prototype and manufacturing gates.

**Tech Stack:** Python 3 standard library and `unittest`; KiCad 10; Konnect MCP/CLI; `kicad-cli`; two-layer JLCPCB rules; Markdown/JSON/SVG/DXF evidence.

## Global Constraints

- The only integration branch is `integration/mcu-tail-ffc`, checked out at `.worktree/mcu-tail-ffc/lh60`; the root checkout remains a clean `master` mirror.
- Create one task branch and one task worktree per task. Merge each verified task into the integration branch, rerun its integration gate, and push the integration branch before starting a dependent task.
- Every task produces an independently reviewable, independently revertible commit. The active commit-attribution hook supplies the single `Co-authored-by: TRAE CLI <traecli@bytedance.com>` trailer; do not add another trailer manually. After each commit, assert `git show -s --format='%B' HEAD | grep -c '^Co-authored-by:'` prints `1`.
- Never edit `*.kicad_sch`, `*.kicad_pcb`, `*.kicad_pro`, `*.kicad_sym`, `*.kicad_mod`, `sym-lib-table`, or `fp-lib-table` as text. All such writes go through Konnect.
- Main- and tail-board PCB writes happen in separate worktrees. KiCad GUI/IPC writes, saves, zone refills, and AppImage-backed `kicad-cli` checks are serialized on this host.
- Both boards remain 2 layers with 0.25 mm minimum trace width, 0.30 mm minimum via drill, 0.70 mm via diameter, and 0.50 mm copper-to-edge. Copper clearance is 0.25 mm everywhere except the exact same-footprint C2856805 pad-to-pad geometry, whose manufacturer-defined 0.20 mm spacing is expressed through the Task 0 custom-rule contract.
- The inter-board connector is exactly XUNPU `FPC-05F-24PH20`, LCSC `C2856805`: 24 pins, 0.50 mm pitch, horizontal SMT, bottom contact, front-flip hinged lid, 2.0 mm high, for a 0.30 +/- 0.03 mm FFC end.
- The FFC carries exactly `COL0..COL9`, `ROW0..ROW6`, six GND conductors, and one no-connect. It never carries `VSYS`, `3V3`, USB, `RUN`, `BOOTSEL`, SWD, or `GP27..GP29`.
- Preserve `COL0..COL9 -> GP0..GP9`, `ROW0..ROW6 -> GP10..GP15, GP26`, QMK `COL2ROW`, 75 physical sockets, and 70 logical nodes.
- The official Waveshare USB adapter is the only supported power source. Tail-board `VSYS` and `3V3` access is measurement-only.
- All 17 series footprints are populated with `0R` by default. A DNP series footprint is an open circuit, not a valid production state.
- U7/U8 PCB work is blocked until the MIF report is complete, approved, committed, merged, and pushed. Do not guess the cable SKU, connector poses, tail outline, mounting stack, or enclosure keepouts.
- Use a fresh evidence directory for every acceptance run; never overwrite historical evidence.

## File and Interface Map

| Responsibility | Files |
|---|---|
| Frozen electrical contract | `tools/lh60_design/interconnect.py`, `tools/verify_interconnect_contract.py` |
| Exact connector library | `tools/lh60_design/interconnect_library.py`, `tools/verify_interconnect_library.py`, `tools/check_interconnect_library_acceptance.py`, `lib/lh60-interconnect/**` |
| Main schematic | `tools/lh60_design/schematic.py`, main schematic tests/checker, `lh60.kicad_sch` |
| Tail project and schematic | `tools/lh60_design/tail_project.py`, `tools/lh60_design/tail_schematic.py`, tail tests/checker, `mcu-tail/*` |
| Mechanical freeze | `tools/check_mif_acceptance.py`, `tools/verify_mif_contract.py`, `docs/mechanical/mcu-tail-mif.*` |
| Main PCB | `tools/lh60_design/pcb.py`, main PCB tests/checker, `lh60.kicad_pcb` |
| Tail PCB | `tools/lh60_design/tail_pcb.py`, tail PCB tests/checker, `mcu-tail/mcu-tail.kicad_pcb` |
| Prototype evidence | `tools/check_prototype_acceptance.py`, `tools/verify_prototype_acceptance.py`, `docs/reports/mcu-tail-prototype-validation.md` |
| Production release | `tools/export_manufacturing.py`, `tools/verify_manufacturing_package.py`, `docs/manufacturing/mcu-tail-release.*`, active baseline docs |

## Dependency and Parallelism

```text
Task 0 Konnect custom rule --+
                              +--> Task 2 U3 library --+
Task 1 U2 contract -----------+                        |
                              +--> Task 3 U4 main sch  |
                              +--> Task 4 U5 tail sch  |
                              +--> Task 5 U6 MIF ------+
                                                       |
                              +------------------------+
                              |                        |
                         Tasks 6-7 U7             Tasks 8-9 U8
                           main PCB                  tail PCB
                              +-----------+------------+
                                          |
                                 prototype fabrication
                                          |
                                    Tasks 10-11 U9
                                          |
                                      Task 12 U10
```

Tasks 3, 4, and the measurement/drawing work for Task 5 may run in parallel after Task 2. Tasks 6-7 and Tasks 8-9 may run in parallel only after Tasks 3-5 are integrated.

Task 2 has one external tooling prerequisite. The C2856805 lands have 0.20 mm
intra-footprint clearance, while the rest of each board must retain 0.25 mm.
KiCad's absolute Board Setup minimum cannot be relaxed by a pad-local override.
Konnect therefore needs a safe custom-rule API so each project can set the hard
floor to 0.20 mm and restore 0.25 mm everywhere except C2856805 pad-to-pad
pairs. Complete Task 0 before Task 2; it does not change LH60 files and may run
in parallel with Task 1.

---

### Task 0: Konnect prerequisite — Add safe conditional custom rules

**Repository/worktree:** `/data00/home/wangqiyilang/playground/konnect`, isolated requirement worktree and integration branch per that repository's instructions

**Files:**
- Modify: `crates/konnect-core/src/tools/verification.rs`
- Modify: `crates/konnect-core/src/router/registry.rs`
- Modify: `tool-directory.md`
- Modify: the verification/design-rule skill documentation exposed by Konnect
- Modify: `crates/konnect/tests/asset_references.rs` only if its documentation-token gate requires it

**Interfaces:**
- Produces: `set_custom_rule(board, name, constraint, minimum_mm, condition, layer=None)` and `list_custom_rules(board)`. The tool atomically upserts one named `.kicad_dru` rule, validates a restricted condition grammar, and preserves unrelated rules.
- Existing `set_design_rules` and `set_layer_constraints` callers remain compatible.

- [ ] **Step 1: Create an isolated Konnect task worktree and read its nearest instructions**

Do not modify the LH60 worktree in this task. Base the task on the current pushed Konnect main/integration state required by that repository.

- [ ] **Step 2: Add failing schema and custom-rule serialization tests**

Extend `verification.rs` tests to require all arguments above, non-empty names, `constraint=clearance`, finite non-negative minimum, and a restricted KiCad condition using item type, footprint reference, and parent/reference navigation. Prove exact rule output, idempotent upsert, preservation of unrelated rules/comments, and stale/invalid input rejection before write.

- [ ] **Step 3: Add a real KiCad DRC coupon test**

Through existing KiCad-aware builders, create a temporary board with two C2856805 footprints and unrelated 0.20/0.24/0.25 mm copper-clearance cases. Set Board Setup minimum to 0.20 mm and add custom rules so only distinct pads within the same C2856805 footprint may use 0.20 mm; require unrelated copper below 0.25 mm to fail DRC and 0.25 mm to pass. Start from a condition using KiCad's `memberOfFootprint()` expression, but freeze the exact syntax only after `kicad-cli pcb drc` proves it on the coupon. The test must prove real KiCad 10 evaluation and priority rather than assuming either.

- [ ] **Step 4: Run focused tests and confirm RED**

Run the repository's focused Rust tests for verification/custom rules and the DRC coupon. Expected: the new tool/schema is missing.

- [ ] **Step 5: Implement the minimal atomic custom-rule API**

Follow the current `set_layer_constraints` CAS-safe named-rule pattern. Accept only the fields in the public schema, escape/reject unsafe names and conditions, atomically upsert by rule name, and add a structured readback operation. Update the verification tool count from 8 to 10 and the generated tool directory. Document KiCad precedence: Board Setup is the hard floor, so LH60 must use 0.20 mm globally plus a 0.25 mm custom rule for every copper pair except the exact same-footprint C2856805 pad pair. Do not add a pad-local override API as a substitute; it cannot lower the Board Setup minimum.

- [ ] **Step 6: Run focused and full Konnect verification**

```bash
cargo fmt --all --check
cargo test -p konnect-core verification --lib
cargo test -p konnect-core --lib --tests
cargo test -p konnect --test asset_references
cargo test --workspace --lib --tests
cargo build --release -p konnect
```

The focused tests, real KiCad coupon, and workspace suite must pass. Stage the verified binary under a new versioned directory such as `~/.local/opt/konnect/<version>-<commit>/konnect`, atomically repoint the existing `~/.local/bin/konnect` symlink after preserving its old target for rollback, then prove the live MCP schemas/readback expose `set_custom_rule` and `list_custom_rules`.

- [ ] **Step 7: Commit, push, integrate, and hand back the deployed commit**

Commit as `feat(verification): add conditional custom rules`, push the task and integration branches according to the Konnect repository workflow, and record its commit and deployed binary digest in the LH60 Task 2 evidence.

---

### Task 1: U2 — Freeze the inter-board Python contract

**Branch/worktree:** `task/mcu-tail-u2-interconnect` at `.worktree/mcu-tail-ffc-u2/lh60`

**Files:**
- Create: `tools/lh60_design/interconnect.py`
- Create: `tools/verify_interconnect_contract.py`

**Interfaces:**
- Consumes: `tools.lh60_design.matrix.gpio_map()`
- Produces: `InterconnectPin`, `ConnectorIdentity`, `CableContract`, `InterboardContract`, `interboard_contract()`, and `reversed_pin_number()`
- Pin 23 is represented as `net_name=None`; no electrical net named `NC` is created.

- [ ] **Step 1: Create the task worktree from the pushed integration branch**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/mcu-tail-u2-interconnect \
  .worktree/mcu-tail-ffc-u2/lh60 origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write the failing contract tests**

Create `tools/verify_interconnect_contract.py` with explicit assertions equivalent to:

```python
import unittest


class InterboardContractTest(unittest.TestCase):
    def test_exact_pin_map_and_connector_identity(self):
        from tools.lh60_design.interconnect import interboard_contract

        contract = interboard_contract()
        self.assertEqual(
            (contract.connector.manufacturer, contract.connector.mpn, contract.connector.lcsc_part),
            ("XUNPU", "FPC-05F-24PH20", "C2856805"),
        )
        self.assertEqual(
            tuple((pin.number, pin.net_name) for pin in contract.pins),
            (
                (1, "GND"), (2, "COL0"), (3, "COL1"), (4, "COL2"),
                (5, "GND"), (6, "COL3"), (7, "COL4"), (8, "COL5"),
                (9, "GND"), (10, "COL6"), (11, "COL7"), (12, "COL8"),
                (13, "COL9"), (14, "ROW0"), (15, "ROW1"), (16, "GND"),
                (17, "ROW2"), (18, "ROW3"), (19, "ROW4"), (20, "GND"),
                (21, "ROW5"), (22, "ROW6"), (23, None), (24, "GND"),
            ),
        )

    def test_passive_reversal_invariant_is_not_a_powered_safety_api(self):
        from tools.lh60_design.interconnect import interboard_contract, reversed_pin_number

        contract = interboard_contract()
        self.assertEqual(contract.ground_pins, frozenset({1, 5, 9, 16, 20, 24}))
        for pin in contract.pins:
            reversed_pin = contract.pin(reversed_pin_number(pin.number))
            self.assertEqual(pin.net_name == "GND", reversed_pin.net_name == "GND")
        self.assertFalse(hasattr(contract, "powered_reversal_is_safe"))

    def test_mif_state_starts_unapproved(self):
        from tools.lh60_design.interconnect import interboard_contract

        cable = interboard_contract().cable
        self.assertIsNone(cable.approved_mif_revision)
        self.assertIsNone(cable.cable_mpn)
        self.assertIsNone(cable.contact_orientation)
```

Also test strict pin numbering `1..24`, signal/GND/NC sets, the exact prohibited-net set, exact GPIO map, `"NC"` absence, and `ValueError` for reversed pin 0 or 25.

- [ ] **Step 3: Run the focused test and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_contract
```

Expected: import failure for `tools.lh60_design.interconnect`.

- [ ] **Step 4: Implement the immutable contract**

Create `tools/lh60_design/interconnect.py` with frozen dataclasses and constructor validation:

```python
from __future__ import annotations

from dataclasses import dataclass

from tools.lh60_design.matrix import gpio_map


@dataclass(frozen=True)
class InterconnectPin:
    number: int
    net_name: str | None

    @property
    def is_no_connect(self) -> bool:
        return self.net_name is None


@dataclass(frozen=True)
class ConnectorIdentity:
    manufacturer: str
    mpn: str
    lcsc_part: str
    datasheet_url: str


@dataclass(frozen=True)
class CableContract:
    pitch_mm: float
    mating_width_mm: float
    mating_width_tolerance_mm: float
    mating_thickness_mm: float
    mating_thickness_tolerance_mm: float
    exposed_conductor_min_mm: float
    stiffener_length_mm: float
    target_max_length_mm: float
    design_max_length_mm: float
    approved_mif_revision: str | None = None
    cable_mpn: str | None = None
    contact_orientation: str | None = None


@dataclass(frozen=True)
class InterboardContract:
    connector: ConnectorIdentity
    pins: tuple[InterconnectPin, ...]
    matrix_gpio_map: tuple[tuple[str, str], ...]
    prohibited_nets: frozenset[str]
    cable: CableContract

    def __post_init__(self) -> None:
        if tuple(pin.number for pin in self.pins) != tuple(range(1, 25)):
            raise ValueError("interconnect pins must be exactly 1..24")
        if self.signal_nets & self.prohibited_nets:
            raise ValueError("FFC signal set includes a prohibited net")

    def pin(self, number: int) -> InterconnectPin:
        if not 1 <= number <= 24:
            raise ValueError(f"pin number outside 1..24: {number}")
        return self.pins[number - 1]

    @property
    def signal_nets(self) -> frozenset[str]:
        return frozenset(pin.net_name for pin in self.pins if pin.net_name not in {None, "GND"})

    @property
    def ground_pins(self) -> frozenset[int]:
        return frozenset(pin.number for pin in self.pins if pin.net_name == "GND")

    @property
    def no_connect_pins(self) -> frozenset[int]:
        return frozenset(pin.number for pin in self.pins if pin.is_no_connect)
```

`interboard_contract()` must return the exact pin table in the test, derive GPIO pairs from `gpio_map()`, use the permanent LCSC PDF URL, and freeze the cable geometry from the approved spec. `reversed_pin_number()` validates `1 <= pin <= 24` before returning `25 - pin`.

- [ ] **Step 5: Run focused and full pure-Python regression**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_contract
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
git diff --check
```

Expected: all tests pass; no KiCad process is required.

- [ ] **Step 6: Commit, push, merge to integration, verify, and push integration**

```bash
git add tools/lh60_design/interconnect.py tools/verify_interconnect_contract.py
git commit -m "feat: freeze MCU tail interconnect contract"
git push -u origin task/mcu-tail-u2-interconnect
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/mcu-tail-u2-interconnect
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_contract
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

---

### Task 2: U3 — Build and audit the exact `C2856805` project library

**Branch/worktree:** `task/mcu-tail-u3-library` at `.worktree/mcu-tail-ffc-u3/lh60`

**Files:**
- Create: `tools/lh60_design/interconnect_library.py`
- Create: `tools/verify_interconnect_library.py`
- Create: `tools/check_interconnect_library_acceptance.py`
- Create through Konnect: `lib/lh60-interconnect/lh60-interconnect.kicad_sym`
- Create through Konnect: `lib/lh60-interconnect/lh60-interconnect.pretty/FPC-05F-24PH20.kicad_mod`
- Create: `lib/lh60-interconnect/README.md`
- Modify through Konnect: `sym-lib-table`, `fp-lib-table`

**Interfaces:**
- Consumes: `interboard_contract()` from Task 1
- Produces: `lh60-interconnect:FPC-05F-24PH20` symbol and footprint, `interconnect_symbol_payload()`, `interconnect_footprint_payload()`, `apply_interconnect_library()`

- [ ] **Step 1: Create the task worktree from the updated integration branch**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/mcu-tail-u3-library \
  .worktree/mcu-tail-ffc-u3/lh60 origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write failing library contract tests**

In `tools/verify_interconnect_library.py`, assert exact symbol identity and all footprint geometry:

```python
class InterconnectFootprintContractTest(unittest.TestCase):
    def test_signal_and_hold_down_pads_match_c2856805(self):
        from tools.lh60_design.interconnect_library import interconnect_footprint_spec

        spec = interconnect_footprint_spec()
        signal = [pad for pad in spec.pads if pad.number]
        hold_downs = [pad for pad in spec.pads if not pad.number]
        self.assertEqual(len(signal), 24)
        self.assertEqual(
            [(pad.number, pad.x, pad.y, pad.width, pad.height) for pad in signal],
            [(str(index + 1), -5.75 + index * 0.5, 0.0, 0.30, 1.25) for index in range(24)],
        )
        self.assertEqual(
            [(pad.x, pad.y, pad.width, pad.height) for pad in hold_downs],
            [(-7.44, 2.575, 2.00, 2.50), (7.44, 2.575, 2.00, 2.50)],
        )
```

Also assert: all pads use `F.Cu/F.Paste/F.Mask`; hold-down numbers are empty; body is 16.40 x 5.12 x 2.00 mm; fab spans `x=-8.20..8.20`, `y=0.68..5.80`; courtyard encloses body and all lands plus 0.25 mm; mouth is on `+Y`; top-view pin 1 is the leftmost signal pad; symbol pins are passive and sequential `1..24`; metadata matches XUNPU/MPN/LCSC/datasheet.

- [ ] **Step 3: Run the focused test and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_interconnect_library
```

Expected: import failure for `interconnect_library`.

- [ ] **Step 4: Implement the library specification and Konnect payloads**

Follow `core_library.py` and `mcu_library.py`. Define frozen `InterconnectPadSpec`, `InterconnectFootprintSpec`, and a 24-pin passive symbol. Generate signal pads with:

```python
tuple(
    InterconnectPadSpec(
        number=str(index + 1),
        x=-5.75 + index * 0.50,
        y=0.0,
        width=0.30,
        height=1.25,
        layers=("F.Cu", "F.Paste", "F.Mask"),
    )
    for index in range(24)
)
```

Append two unnumbered mechanical SMD pads at `(-7.44, 2.575)` and `(7.44, 2.575)`, size 2.00 x 2.50 mm, with the same copper/paste/mask layers. A live temporary-coupon probe against Konnect 0.6.1 has confirmed that `create_footprint` accepts and serializes an empty pad number; keep a regression test for this contract before touching the project library. If future readback cannot distinguish the two unnumbered pads, extend its output or verify the exact count/geometry through a KiCad-aware export; do not fall back to direct text editing or numbered 25/26 pads. Use `set_footprint_graphics` for exact `F.Fab`, `F.CrtYd`, `F.SilkS`, pin-1 marker, and cable-mouth graphics; use `set_footprint_metadata` for the exact part description and tags. Do not associate an approximate STEP model.

The 0.30 mm pads at 0.50 mm pitch leave 0.20 mm copper clearance, below the project's 0.25 mm general rule. Use the deployed Task 0 tool to set Board Setup's absolute minimum to 0.20 mm and add an audited 0.25 mm custom rule for every copper pair except distinct pads within the same C2856805 footprint. Apply the rule to both projects, read it back, and rerun the real KiCad coupon plus board DRC. Do not use a pad-local override to try to bypass a 0.25 mm Board Setup minimum, and do not leave the rest of either board at 0.20 mm.

- [ ] **Step 5: Implement the live acceptance checker**

`tools/check_interconnect_library_acceptance.py` must query `get_symbol_info` and `get_footprint_info(include_graphics=true)`, compare every pad/graphic against the Python spec, and prove project-scoped `${KIPRJMOD}` registrations. It must reject pad 25/26, numbered hold-downs, missing Paste/Mask, a mirrored pin order, wrong mouth direction, or any FH12 identity.

- [ ] **Step 6: Add provenance documentation**

`lib/lh60-interconnect/README.md` records the exact product URL, permanent LCSC PDF, XUNPU series drawing, retrieval date, EasyEDA component/footprint UUIDs, dimensions, top-view convention, absence of an exact trusted STEP, and why FH12 is not a drop-in replacement.

- [ ] **Step 7: Apply and register the protected library through Konnect**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.interconnect_library --apply
PYTHONDONTWRITEBYTECODE=1 python tools/check_interconnect_library_acceptance.py
```

Expected: one symbol, one footprint, 24 electrical pads plus two unnumbered mechanical lands, exact graphics, and portable project registrations. No direct file edit is permitted.

- [ ] **Step 8: Run focused and full regression**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_interconnect_contract \
  tools.verify_interconnect_library
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
git diff --check
```

- [ ] **Step 9: Commit, push, integrate, and push integration**

```bash
git add tools/lh60_design/interconnect_library.py \
  tools/verify_interconnect_library.py \
  tools/check_interconnect_library_acceptance.py \
  lib/lh60-interconnect sym-lib-table fp-lib-table
git commit -m "feat: add C2856805 interconnect library"
git push -u origin task/mcu-tail-u3-library
git -C .worktree/mcu-tail-ffc/lh60 merge --no-ff task/mcu-tail-u3-library
PYTHONDONTWRITEBYTECODE=1 python tools/check_interconnect_library_acceptance.py
git -C .worktree/mcu-tail-ffc/lh60 push origin integration/mcu-tail-ffc
```

---

### Task 3: U4 — Migrate the main schematic to the passive FFC matrix board

**Branch/worktree:** `task/mcu-tail-u4-main-schematic` at `.worktree/mcu-tail-ffc-u4/lh60`

**Files:**
- Modify: `tools/lh60_design/schematic.py`
- Modify: `tools/verify_schematic_contract.py`
- Modify: `tools/verify_schematic_apply.py`
- Modify: `tools/check_schematic_acceptance.py`
- Modify: `tools/verify_schematic_acceptance.py`
- Modify through Konnect: `lh60.kicad_sch`

**Interfaces:**
- Consumes: `interboard_contract()` and `lh60-interconnect:FPC-05F-24PH20`
- Produces: root `SchematicPlan` containing 75 switches, 70 diodes, one FFC connector, no MCU, no power flags, and one explicit no-connect at `J1.23`

- [ ] **Step 1: Create the task worktree after Tasks 1-2 are integrated**

```bash
git fetch origin integration/mcu-tail-ffc
git worktree add -b task/mcu-tail-u4-main-schematic \
  .worktree/mcu-tail-ffc-u4/lh60 origin/integration/mcu-tail-ffc
```

- [ ] **Step 2: Write failing plan and acceptance tests**

Update `tools/verify_schematic_contract.py` to require exact inventory and nets:

```python
self.assertEqual(
    Counter(component.kind for component in plan.components),
    Counter({"switch": 75, "diode": 70, "connector": 1}),
)
self.assertEqual([c.reference for c in plan.components if c.kind == "connector"], ["J1"])
self.assertFalse(any(c.kind in {"mcu", "power_flag"} for c in plan.components))
self.assertEqual(plan.no_connects, (NoConnectPin("J1", "23"),))
```

Assert `J1.1..24` matches Task 1 for every non-NC pin, the existing 290 matrix pin assignments are unchanged, field visibility contains 146 components, and forbidden power/USB/spare nets do not exist. Update acceptance tests to freeze 146 components and 313 net labels plus one no-connect marker.

- [ ] **Step 3: Run tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_schematic_contract \
  tools.verify_schematic_apply \
  tools.verify_schematic_acceptance
```

Expected: old `U1 + J1..J6 + #FLG01..03` inventory fails.

- [ ] **Step 4: Change the main schematic plan without touching the PCB**

Add `NoConnectPin(reference: str, pin_number: str)` and `SchematicPlan.no_connects`. Remove MCU/debug-header/power-flag constants and builders. Build `J1` from `interboard_contract()`, using `lh60-interconnect:FPC-05F-24PH20` for both `lib_id` and `footprint`, and fields `Manufacturer`, `MPN`, and `LCSC`. Preserve all matrix builders byte-for-behavior.

- [ ] **Step 5: Extend the Konnect apply path for pin-level no-connects**

Require `get_schematic_pin_locations` and `batch_add_no_connect` in the capability gate. After placement and symbol refresh, resolve the actual endpoint for `J1.23`, then call:

```python
client.call_tool(
    "batch_add_no_connect",
    {
        "schematic": str(schematic),
        "positions": [{"x": pin_23["x"], "y": pin_23["y"]}],
    },
)
```

Tests fail closed on missing/duplicate pin 23, non-finite coordinates, or missing tool schemas. Delete U1-specific library-refresh and field-reset calls.

- [ ] **Step 6: Add a current-155 to passive-146 migration transaction**

Do not reuse the old 172-component convergence path. Add a transaction that proves the exact current 155-component source and root-PCB SHA, accepts a temporary candidate plus manual visual approval, deletes existing schematic content through Konnect, applies the new plan once, accepts production and a second candidate as semantically identical, and proves the PCB hash unchanged.

- [ ] **Step 7: Build and visually approve a temporary candidate**

```bash
candidate_dir=$(mktemp -d /tmp/lh60-main-ffc-candidate.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python tools/check_schematic_acceptance.py \
  --candidate-dir "$candidate_dir" \
  --output "$candidate_dir/acceptance.json"
```

Inspect J1 pin order, NC marker, fields, matrix readability, and title-block clearance; record approval bound to git, plan, SVG, and render hashes.

- [ ] **Step 8: Apply and verify the production schematic through Konnect**

Run the new transaction with the exact candidate evidence. Do not update the PCB. Then run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_interconnect_contract \
  tools.verify_schematic_contract \
  tools.verify_schematic_apply \
  tools.verify_schematic_acceptance
PYTHONDONTWRITEBYTECODE=1 python tools/check_schematic_acceptance.py --production
git diff --check
```

Expected: ERC 0/0, exact 146-component inventory, one NC, accepted render, and unchanged `lh60.kicad_pcb` hash.

- [ ] **Step 9: Commit, push, integrate, reverify, and push integration**

Commit all U4 files as `feat(sch): move matrix interface to FFC`, push the task branch, merge it with `--no-ff` into integration, rerun production acceptance there, and push integration.

---

### Task 4: U5 — Create the MCU-tail project and schematic

**Branch/worktree:** `task/mcu-tail-u5-tail-schematic` at `.worktree/mcu-tail-ffc-u5/lh60`

**Files:**
- Create: `tools/lh60_design/tail_project.py`
- Create: `tools/lh60_design/tail_schematic.py`
- Create: `tools/check_tail_schematic_acceptance.py`
- Create: `tools/verify_tail_project_contract.py`
- Create: `tools/verify_tail_schematic_contract.py`
- Create: `tools/verify_tail_schematic_apply.py`
- Create: `tools/verify_tail_schematic_acceptance.py`
- Create: `mcu-tail/README.md`
- Create through Konnect: `mcu-tail/mcu-tail.kicad_pro`, `mcu-tail/mcu-tail.kicad_sch`, and blank `mcu-tail/mcu-tail.kicad_pcb`

**Interfaces:**
- Consumes: Task 1 contract, Task 2 connector library, `lh60-mcu:RP2040-Tiny`, `Device:R`, and existing project-local debug connector assets
- Produces: `build_tail_schematic_plan()` and an accepted 24-component tail schematic

- [ ] **Step 1: Create the task worktree after Tasks 1-2 are integrated**

Create `task/mcu-tail-u5-tail-schematic` from the pushed integration branch. It must not modify any root schematic generator/checker file owned by Task 3.

- [ ] **Step 2: Freeze the tail schematic contract in failing tests**

Use this exact reference contract:

```text
U1                 RP2040-Tiny
J1                 C2856805 FFC
R1..R10            MCU_COL0..MCU_COL9 -> COL0..COL9, value 0R
R11..R17           MCU_ROW0..MCU_ROW6 -> ROW0..ROW6, value 0R
J2 PWR_MON         VSYS, 3V3, GND; measurement-only fields
J3 AUX             GP27, GP28, GP29
#FLG01..03          VSYS, 3V3, GND; on_board=False
J1.23              explicit no-connect
```

Freeze `Resistor_SMD:R_0603_1608Metric` for all 17 series resistors. Tests require 24 total components: 1 MCU, 17 resistors, 3 connectors, and 3 flags. They prove that only the corresponding 0R bridges each `MCU_*` net to its FFC-side net.

- [ ] **Step 3: Run focused tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_tail_project_contract \
  tools.verify_tail_schematic_contract \
  tools.verify_tail_schematic_apply \
  tools.verify_tail_schematic_acceptance
```

Expected: missing modules/project.

- [ ] **Step 4: Implement `tail_project.py`**

Follow `project.py`: create `mcu-tail/` with name `mcu-tail`, register `lh60-mcu`, `lh60-core`, and `lh60-interconnect` through Konnect using portable `${KIPRJMOD}/../lib/...` URIs, and apply the same two-layer rules. Do not set the final board outline; Task 8 consumes MIF for that.

- [ ] **Step 5: Implement `tail_schematic.py` and its capability gate**

Keep tail dataclasses/functions in this file so Task 3 and Task 4 have disjoint writes. Use the same batch placement/edit/connect pattern and endpoint-based NC logic. Build MCU-side nets from `interboard_contract().matrix_gpio_map`; connect every FFC-side signal through exactly one 0R. Mark J2 access with `MeasurementOnly=true`.

- [ ] **Step 6: Record the controlled Waveshare USB assembly baseline**

`mcu-tail/README.md` identifies RP2040-Tiny V1.1, the official 8-pin adapter/FPC revision or traceable supplied baseline, source schematic, CC/VBUS/D+/D-/ESD/shield audit, no-USB-stub rule, external USB-C hot-plug allowance, and internal 8-pin-FPC power-off service rule.

- [ ] **Step 7: Create the protected project and apply through Konnect**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.tail_project --apply
PYTHONDONTWRITEBYTECODE=1 python -m tools.lh60_design.tail_schematic --apply
```

The blank PCB is created once and then left untouched; Task 8 owns its synchronization and layout.

- [ ] **Step 8: Run candidate/live acceptance**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v \
  tools.verify_interconnect_contract \
  tools.verify_tail_project_contract \
  tools.verify_tail_schematic_contract \
  tools.verify_tail_schematic_apply \
  tools.verify_tail_schematic_acceptance
PYTHONDONTWRITEBYTECODE=1 python tools/check_tail_schematic_acceptance.py --production
git diff --check
```

Expected: ERC 0/0, exact inventory/net/NC contract, no unexpected short/orphan/single-pin result, and approved SVG.

- [ ] **Step 9: Commit, push, integrate, and push integration**

Commit as `feat(sch): add RP2040 MCU tail project`, push the task branch, merge into integration, rerun tail acceptance there, and push integration.

---

### Task 5: U6 — Freeze the mechanical interface before PCB work

**Branch/worktree:** `task/mcu-tail-u6-mif` at `.worktree/mcu-tail-ffc-u6/lh60`

**Files:**
- Create: `docs/mechanical/mcu-tail-mif.md`
- Create: `docs/mechanical/mcu-tail-mif.json`
- Create: `docs/mechanical/mcu-tail-interface.svg`
- Create: `docs/mechanical/mcu-tail-interface.dxf`
- Create: `tools/check_mif_acceptance.py`
- Create: `tools/verify_mif_contract.py`

**Interfaces:**
- Consumes: `InterboardContract`, exact Task 2 footprint geometry, enclosure/plate measurements, selected cable datasheet, and RP2040/USB-adapter geometry
- Produces: `MifContract`, `load_mif(path: Path) -> MifContract`, `assert_mif_approved(contract, expected_git_sha)`, and the approved JSON revision consumed by Tasks 6-9

- [ ] **Step 1: Create the task worktree and collect controlled mechanical inputs**

Create `task/mcu-tail-u6-mif` from integration. Record the case/plate revision, measured datum scheme, RP2040-Tiny STEP, exact USB adapter and 8-pin FPC baseline, C2856805 body/actuator evidence, and candidate purchasable FFC datasheets. If enclosure geometry or an actual cable choice is unavailable, complete the schema/checker but leave `approval.status=blocked`; Tasks 6-9 may not start.

- [ ] **Step 2: Write failing schema and gate tests**

`tools/verify_mif_contract.py` builds complete and mutated fixtures. The complete fixture contains `schema_version`, `interface_revision`, `source_git_sha`, an exact cable identity and end geometry, main/tail connector poses, relative board poses, tail outline, board thickness, at least two M2 holes and hardware stack, USB-adapter datum, mechanical/user keepouts, assembly steps, strain-relief thresholds, and an approval object.

Tests reject missing cable MPN, non-finite or zero geometry, ambiguous contact orientation, absent 1-to-1 proof, fewer than two mounting holes, missing USB-adapter datum, missing keepouts/assembly sequence/load thresholds, stale source SHA, or non-approved status.

- [ ] **Step 3: Run tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_mif_contract
```

Expected: missing checker or missing MIF files.

- [ ] **Step 4: Implement the parser and fail-closed checker**

Use frozen dataclasses for cable, connector pose, board pose, mounting hole/stack, keepout, and acceptance thresholds. `check_mif_acceptance.py` loads JSON, verifies SVG/DXF hashes named in the JSON, validates `pin 1 -> conductor 1 -> pin 1`, and refuses approval if a source file or task integration SHA has drifted.

- [ ] **Step 5: Produce and review the mechanical package**

The Markdown and drawings show one named observation face for both boards, connector mouths/contact faces, conductor 1, relative XYZ/rotation, tail outline, M2 stack, USB-adapter independent support, open-latch/tool/insertion/stiffener/first-bend/service-loop/enclosure keepouts, normal-use and cover-removed states, and ordered assembly/disassembly. Use Konnect read/export tools for board data; do not edit KiCad files during U6.

- [ ] **Step 6: Verify and obtain explicit approval**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_mif_contract
PYTHONDONTWRITEBYTECODE=1 python tools/check_mif_acceptance.py --mif docs/mechanical/mcu-tail-mif.json
git diff --check
```

Expected: `APPROVED` only after reviewer identity/date and exact source hashes are present. Otherwise stop here with `BLOCKED`; never invent geometry to unblock PCB work.

- [ ] **Step 7: Commit, push, integrate, and push integration**

Commit as `docs: freeze MCU tail mechanical interface`, push, merge into integration, rerun the checker there, and push integration.

---

### Task 6: U7a — Migrate the root PCB inventory and place the FFC connector

**Branch/worktree:** `task/mcu-tail-u7-main-pcb-place` at `.worktree/mcu-tail-ffc-u7a/lh60`

**Files:**
- Modify: `tools/lh60_design/pcb.py`
- Modify: `tools/verify_pcb_sync.py`
- Modify: `tools/verify_pcb_placement.py`
- Modify through Konnect: `lh60.kicad_pcb`

**Interfaces:**
- Consumes: accepted main schematic and approved `MifContract.main_connector`
- Produces: root board with 75 switches, 70 diodes, and one C2856805 at the exact MIF pose; no U1/J2-J6 legacy footprints

- [ ] **Step 1: Create the task worktree only after Tasks 3 and 5 are integrated**

Assert `check_mif_acceptance.py` passes before any PCB tool call. Open the root board in one Xvfb-backed KiCad PCB session and ensure no other PCB writer is active.

- [ ] **Step 2: Write failing inventory, sync, and pose tests**

Freeze exact reference sets and counts, connector pad map, MIF pose, pin-1 direction, cable-mouth direction, and removal of U1/J2-J6. Tests reject stale MIF, unexpected board hash, partial schematic-to-PCB coverage, missing pads, or boolean/non-finite pose evidence.

- [ ] **Step 3: Run focused tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_sync tools.verify_pcb_placement
```

- [ ] **Step 4: Dry-run and atomically apply schematic-to-PCB migration**

Call `update_pcb_from_schematic(dry_run=true)`, inspect status/coverage/diagnostics and exact add/remove inventory, then apply only with its returned `expected_plan_revision`. Place J1 with `batch_set_component_poses` using the exact MIF pose. Save once and re-query inventory, pads, and pose.

- [ ] **Step 5: Resolve the MIF keepout-tool gate**

Konnect 0.6.1 currently lacks general mechanical/user-keepout authoring. Before placement is accepted, either add that capability in Konnect and use it, or execute an explicitly approved KiCad-GUI operation and verify it through export/readback. Direct `.kicad_pcb` editing, copper-zone substitutes, or skipping the keepout are prohibited.

- [ ] **Step 6: Verify, commit, and integrate**

Run focused tests plus `get_component_list`, `get_component_pads`, `get_board_extents`, MIF keepout readback/export, and a fresh SVG/3D visual review. Commit as `feat(pcb): place main-board FFC interface`, push, merge, reverify, and push integration.

---

### Task 7: U7b — Route and accept the root passive matrix PCB

**Branch/worktree:** `task/mcu-tail-u7-main-pcb-route` at `.worktree/mcu-tail-ffc-u7b/lh60`

**Files:**
- Modify: `tools/check_pcb_acceptance.py`
- Modify: `tools/verify_pcb_acceptance.py`
- Modify: `tools/lh60_design/pcb.py` only if routing helpers are required
- Modify through Konnect: `lh60.kicad_pcb`
- Create: `docs/reports/mcu-tail-main-pcb.md`

**Interfaces:**
- Consumes: Task 6 placed root board and MIF keepouts
- Produces: fully routed passive keyboard board with continuous connector-reference copper and zero unconnected matrix/FFC endpoints

- [ ] **Step 1: Write failing production acceptance tests**

Replace old `152 refs / J1..J6 / 163 violations / 367 unconnected` expectations. Require exact 146-footprint inventory, no U1/J2-J6, J1 exact pads/nets/NC, no forbidden nets/components, zero DRC errors, zero unconnected matrix/FFC items, clear MIF keepouts, pin-1/mouth SVG evidence, and unchanged board hash across read-only acceptance.

- [ ] **Step 2: Run focused tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_pcb_acceptance
```

- [ ] **Step 3: Route through Konnect in one serialized PCB session**

Route all 17 FFC signals and six GND contacts; keep connector escape over continuous reference copper and add stitching on layer changes. Keep the effective routing and unrelated-copper clearance at 0.25 mm. The Board Setup hard floor is 0.20 mm only so the Task 0 custom rule can admit the footprint's own adjacent pads; the complementary custom rule restores 0.25 mm elsewhere. Refill zones and save at explicit checkpoints.

- [ ] **Step 4: Run live DRC/DFM and render review**

```bash
evidence_root=$(mktemp -d /tmp/lh60-main-pcb-acceptance.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python tools/check_pcb_acceptance.py \
  --production --board lh60.kicad_pcb --output-dir "$evidence_root"
```

Run Konnect DRC, manufacturing validation, front/back SVG, 3D export, inventory, and pad readback. Expected: zero DRC errors, zero unconnected matrix/FFC endpoints, and approved mechanical/visual evidence.

- [ ] **Step 5: Commit, push, integrate, and push integration**

Commit as `feat(pcb): route passive matrix FFC board`, push, merge into integration, rerun acceptance with a new evidence directory, and push integration.

---

### Task 8: U8a — Synchronize and place the MCU-tail PCB

**Branch/worktree:** `task/mcu-tail-u8-tail-pcb-place` at `.worktree/mcu-tail-ffc-u8a/lh60`

**Files:**
- Create: `tools/lh60_design/tail_pcb.py`
- Create: `tools/verify_tail_pcb.py`
- Modify through Konnect: `mcu-tail/mcu-tail.kicad_pcb`

**Interfaces:**
- Consumes: accepted tail schematic and complete MIF tail outline/poses/mounting holes/keepouts
- Produces: synchronized tail PCB with exact inventory and placed components

- [ ] **Step 1: Create the worktree only after Tasks 4 and 5 are integrated**

Require approved MIF and serialize all PCB IPC activity against Tasks 6-7.

- [ ] **Step 2: Write failing placement tests**

Tests derive inventory from `build_tail_schematic_plan()` and require one MCU, one C2856805, R1-R17 at 0R, J2/J3 access, at least two MIF-defined mounting holes, exact outline/poses, no courtyard/keepout collision, and correct connector pin/mouth direction.

- [ ] **Step 3: Run tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_tail_pcb
```

- [ ] **Step 4: Apply outline, holes, schematic sync, and poses through Konnect**

Use `set_board_size` or `add_board_outline` from MIF, `add_mounting_hole` for MIF holes, revision-gated `update_pcb_from_schematic`, and `batch_set_component_poses` for all components. Apply the same approved keepout mechanism as Task 6, save once, and re-query every pose/pad.

- [ ] **Step 5: Verify, commit, and integrate**

Run placement tests, placement-only DRC, SVG/3D inspection, and `git diff --check`. Commit as `feat(pcb): place RP2040 MCU tail`, push, merge, reverify, and push integration.

---

### Task 9: U8b — Route and accept the MCU-tail PCB

**Branch/worktree:** `task/mcu-tail-u8-tail-pcb-route` at `.worktree/mcu-tail-ffc-u8b/lh60`

**Files:**
- Create: `tools/check_tail_pcb_acceptance.py`
- Create: `tools/verify_tail_pcb_acceptance.py`
- Modify: `tools/lh60_design/tail_pcb.py` if routing helpers are required
- Modify through Konnect: `mcu-tail/mcu-tail.kicad_pcb`
- Create: `docs/reports/mcu-tail-tail-pcb.md`

**Interfaces:**
- Consumes: Task 8 placed tail board
- Produces: routed tail board with all 17 default 0R links, local access, ground reference, and complete MIF/USB keepout compliance

- [ ] **Step 1: Write failing acceptance tests**

Require exact schematic-derived inventory, 17 populated `0R` values/footprints, correct two-sided net bridges, no forbidden FFC nets, measurement-only power access, zero DRC/unconnected items, MIF keepout compliance, PnP/BOM semantics, and immutable read-only acceptance hashes.

- [ ] **Step 2: Run tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_tail_pcb_acceptance
```

- [ ] **Step 3: Route and pour through Konnect**

Create/assign netclasses, route MCU GPIO to MCU-side resistor nets and resistor outputs to J1, route local access, add/refill GND zones, and keep USB/FPC/mechanical volumes clear. Do not add USB D+/D- routing: it remains on the vendor assembly.

- [ ] **Step 4: Run live acceptance**

```bash
evidence_root=$(mktemp -d /tmp/lh60-tail-pcb-acceptance.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 python tools/check_tail_pcb_acceptance.py \
  --production --board mcu-tail/mcu-tail.kicad_pcb \
  --output-dir "$evidence_root"
```

Expected: zero DRC errors/unconnected items, valid BOM/PnP roles, approved SVG/3D and MIF envelopes, and unchanged board hash during acceptance.

- [ ] **Step 5: Commit, push, integrate, and push integration**

Commit as `feat(pcb): route RP2040 MCU tail`, push, merge, rerun with a fresh evidence directory, and push integration.

---

### Task 10: U9a — Define the prototype evidence schema and checker

**Branch/worktree:** `task/mcu-tail-u9-prototype-checker` at `.worktree/mcu-tail-ffc-u9a/lh60`

**Files:**
- Create: `tools/check_prototype_acceptance.py`
- Create: `tools/verify_prototype_acceptance.py`
- Create: `docs/reports/mcu-tail-prototype-validation.md`

**Interfaces:**
- Consumes: MIF revision, main/tail PCB SHAs, cable identity, firmware SHA, instrument IDs, and raw-evidence hashes
- Produces: `PrototypeEvidence`, `load_prototype_evidence(path)`, and `assert_prototype_accepted(evidence, expected_revision)` for Task 12

- [ ] **Step 1: Create the worktree after Tasks 7 and 9 are integrated**

The checker may be implemented before hardware arrives, but fixtures must be explicitly synthetic and cannot be mistaken for production evidence.

- [ ] **Step 2: Write failing checker tests**

The valid fixture names integration/main/tail/MIF/cable/firmware/instrument identities and records pass/fail plus raw-evidence SHA-256 for: all 24 continuity paths; six GND and NC checks; unpowered 1-to-24 fault fixture; USB-only power/backfeed/inrush; all 75 sockets and 70 logical nodes; row/column/aggressor/multi-key SI; zero-error soak; ESD; seating/locks/marking/pinch/pull/vibration/intermittency; and separate mating-life samples.

Mutated fixtures must reject absent thresholds, missing socket/channel IDs, wrong cable length, stale hashes, `waived`/`provisional`, failed checks, or a production unit reused as a life-test sample.

- [ ] **Step 3: Run tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_prototype_acceptance
```

- [ ] **Step 4: Implement the strict parser/checker**

Use frozen dataclasses and strict JSON types; reject booleans where finite numbers are required. Recompute raw evidence hashes, bind every identity to integration state, and emit exactly `PASS`, `FAIL`, or `INCOMPLETE`. Only `PASS` unblocks Task 12.

- [ ] **Step 5: Write the executable lab protocol**

The report specifies setup, connection order, instruments, commands, channel/socket table, waveform captures, ESD injection, mechanical load directions, safety stops, thresholds, evidence names, and the separation between type-test samples and production EOL.

- [ ] **Step 6: Verify, commit, and integrate**

Run the focused test and `git diff --check`; commit as `test: add MCU tail prototype acceptance`, push, merge, reverify, and push integration.

---

### Task 11: U9b — Execute prototype validation and bind evidence

**Branch/worktree:** `task/mcu-tail-u9-prototype-evidence` at `.worktree/mcu-tail-ffc-u9b/lh60`

**Files:**
- Modify: `docs/reports/mcu-tail-prototype-validation.md`
- Create: `docs/reports/mcu-tail-prototype-validation.json`
- Store raw evidence outside Git in a fresh immutable directory and record its SHA-256 values

**Interfaces:**
- Consumes: manufactured prototypes, controlled FFC, and Task 10 protocol
- Produces: a `PASS` result bound to exact hardware/firmware/tool revisions

- [ ] **Step 1: Start only when physical hardware and instruments exist**

If a board, controlled cable, fixture, or calibrated instrument is absent, report U9 as externally blocked; never fabricate or waive evidence.

- [ ] **Step 2: Create a fresh evidence root and record identities**

```bash
evidence_root=$(mktemp -d /tmp/lh60-mcu-tail-prototype.XXXXXX)
echo "$evidence_root"
```

Record board serial/fab lots, cable lot/length, integration and firmware SHAs, and instrument IDs before power-on.

- [ ] **Step 3: Execute unpowered continuity and assembly inspection**

Measure all 24 1-to-1 paths, grounds, NC isolation, and the unpowered 1-to-24 fixture. Record full insertion, closed locks, conductor-1 marks, service loop, clamp, M2 stack, USB support, and absence of folds/scrapes/pinches.

- [ ] **Step 4: Execute power, functional, SI, soak, ESD, and mechanical tests**

Use precommitted thresholds. Test USB-only power/backfeed/inrush; every physical socket/logical node; worst-case row/column/aggressor/multi-key waveforms; zero-error soak; ESD; pull/vibration/intermittency; and separate type-life samples. Save raw files under the evidence root.

- [ ] **Step 5: Generate and validate the bound JSON**

```bash
PYTHONDONTWRITEBYTECODE=1 python tools/check_prototype_acceptance.py \
  --results docs/reports/mcu-tail-prototype-validation.json
```

Expected: `PASS`. Any failure or incompleteness stops Task 12 and routes to the owning upstream unit.

- [ ] **Step 6: Commit, push, integrate, and push integration**

Commit report and bound JSON, not bulky raw instrument files, as `test: validate MCU tail prototype`; push, merge, reverify, and push integration.

---

### Task 12: U10 — Export and verify the production package

**Branch/worktree:** `task/mcu-tail-u10-manufacturing` at `.worktree/mcu-tail-ffc-u10/lh60`

**Files:**
- Create: `tools/export_manufacturing.py`
- Create: `tools/verify_manufacturing_package.py`
- Create: `docs/manufacturing/mcu-tail-release.md`
- Create: `docs/manufacturing/mcu-tail-release-manifest.json`
- Modify: `docs/current-baseline.md`
- Modify: `docs/glossary.md` only if a new public term is introduced
- Generate outside Git: `FabOutput/<revision>/{main,tail,cable}/**`

**Interfaces:**
- Consumes: accepted boards/schematics, approved MIF, and Task 11 `PASS` evidence
- Produces: two JLCPCB packages, cable procurement package, and committed SHA-256 manifest

- [ ] **Step 1: Create the worktree only after Task 11 passes**

The exporter calls `assert_prototype_accepted()` before any package can be marked releasable.

- [ ] **Step 2: Write failing package tests**

Require `main/` and `tail/` Gerber, drill, BOM, positions, STEP, assembly PDF; `cable/` procurement and incoming-inspection PDFs; exact Git/KiCad/MIF/prototype identities and hashes; and correct BOM/PnP roles. Reject missing/stale outputs, unexplained ERC/DRC/DFM, or manifest files absent on disk.

- [ ] **Step 3: Run tests and confirm RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v tools.verify_manufacturing_package
```

- [ ] **Step 4: Implement the serialized two-board exporter**

For main and tail serially run ERC, DRC, design review, JLCPCB validation, Gerber/drill/BOM/position/STEP/assembly-PDF exports, and independent readback. Any design-review `partial`/`failed`, DFM non-ready state, unexplained ERC/DRC finding, or unconnected matrix/FFC item fails.

Enforce: main sockets BOM yes/PnP no; 70 diodes BOM/PnP yes; both C2856805 parts follow the approved assembly strategy; RP2040-Tiny BOM/manual/PnP no; R1-R17 are `0R` and BOM/PnP yes; mounting holes/mechanical items PnP no.

- [ ] **Step 5: Export and verify a fresh package**

```bash
revision=$(git rev-parse --short=12 HEAD)
PYTHONDONTWRITEBYTECODE=1 python tools/export_manufacturing.py \
  --revision "$revision" --output "FabOutput/$revision"
PYTHONDONTWRITEBYTECODE=1 python tools/verify_manufacturing_package.py \
  "FabOutput/$revision"
```

Expected: `READY`; the committed manifest names every output, SHA-256, tool version, source SHA, and KiCad source SHA.

- [ ] **Step 6: Update active baseline and release runbook**

Update `docs/current-baseline.md` to the two-board architecture and link the design, MIF, PCB reports, prototype report, and release manifest. The release runbook records ordering, stack/rules, assembly sides, manual steps, cable MPN/orientation/length, incoming inspection, EOL, and rework. Preserve historical debug-header reports.

- [ ] **Step 7: Run final clean integration verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tools -p 'verify_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python tools/check_schematic_acceptance.py --production
PYTHONDONTWRITEBYTECODE=1 python tools/check_tail_schematic_acceptance.py --production
PYTHONDONTWRITEBYTECODE=1 python tools/check_pcb_acceptance.py --production \
  --output-dir "$(mktemp -d /tmp/lh60-main-final.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 python tools/check_tail_pcb_acceptance.py --production \
  --output-dir "$(mktemp -d /tmp/lh60-tail-final.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 python tools/check_prototype_acceptance.py \
  --results docs/reports/mcu-tail-prototype-validation.json
git diff --check
git status --short
```

- [ ] **Step 8: Commit, push, integrate, and push final delivery**

Commit as `release: package external MCU tail design`, push, merge with `--no-ff` into integration, rerun Step 7 from integration, push `integration/mcu-tail-ffc`, and retain the integration worktree until user review completes.

---

## Execution Checkpoints

- After Task 1: electrical pin and GPIO interface frozen.
- After Task 2: exact connector library and connector-local 0.20 mm pad-clearance solution frozen.
- After Tasks 3-4: both schematics accepted independently; no PCB mutation has occurred.
- After Task 5: physical cable, board poses, mounting, keepouts, and service procedure approved.
- After Tasks 6-9: both boards routed and independently accepted.
- After Task 11: real prototype evidence is `PASS`.
- After Task 12: production files and active documentation are ready for ordering.
