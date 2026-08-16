# LH60 RP2040 V2 Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the disposable test workspace with one clean production KiCad project for the approved 15u × 5-row LH60 layout, a 21-footprint G/K/Dual socket library, an audited RP2040-Tiny module, a 10 × 7 COL2ROW matrix, and a JLC-ready routed PCB.

**Architecture:** `tools/lh60_design/` is the deterministic non-KiCad source of truth for socket geometry, the frozen physical layout, matrix-node allocation, GPIO mapping, and regional clearance reports. Every KiCad source mutation is executed through Konnect MCP; Python tests read outputs and call KiCad CLI but never write protected files. The production schematic is completed before PCB placement; KiCad 10’s **Tools → Update PCB from Schematic** is an explicit GUI gate because no supported CLI/MCP replacement exists.

**Tech Stack:** Python 3.14, `unittest`, Shapely 2.x, Rust/Konnect MCP, KiCad 10.0.5 CLI/UI, JLCPCB current standard 2-layer process.

## Global Constraints

- Work only on integration branch `lh60-rp2040-v2` in this worktree.
- Every completed unit is verified, committed, and pushed before the next dependent unit.
- Every commit message ends exactly once with `Co-authored-by: TRAE CLI <noreply@bytedance.com>`.
- Never edit `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, `.kicad_sym`, `.kicad_mod`, `fp-lib-table`, or `sym-lib-table` directly.
- The production project is created from blank files; no KiCad item is copied from `test/`, an old production board, or an archived project.
- The approved physical baseline is 15u × 5 rows at 19.05 mm pitch, arrow-key bottom row, no ISO Enter, and the four approved multi-layout regions.
- The production matrix is frozen at 10 columns × 7 rows for the current 70 logical nodes, using 17 GPIO and leaving GP17–GP25 physically unavailable and GP29/GP28/GP27 available only if not allocated below.
- Matrix GPIO contract: `COL0..COL9 = GP0..GP9`; `ROW0..ROW6 = GP10..GP15, GP26`; spare pads are `GP27`, `GP28`, and `GP29`.
- Every logical node has exactly one `1N4148WS` diode in SOD-323 and uses QMK `COL2ROW`.
- All electronics, sockets, and test pads are bottom-side; the front side is reserved for switches and a future plate.
- Socket footprint `B.CrtYd` encloses the physical socket and complete land pattern with 0.50 mm clearance.
- PCB design rules: 0.25 mm signal width, 0.25 mm copper clearance, 0.50 mm minimum power width, 0.30/0.70 mm via drill/diameter, 0.50 mm copper-to-CNC-edge, and 0.50 mm target/0.45 mm hard minimum independent component-hole edge clearance.
- No mounting holes, PCB stabilizer holes, RGB, encoder, buzzer, battery, wireless, extra USB, SWD, RUN, BOOTSEL, or decorative silkscreen.
- If one multi-layout region has no simultaneous-socket solution, record the measured conflict and request user approval for that region; continue all non-dependent work.

---

## File Structure

| Path | Responsibility |
|---|---|
| `tools/lh60_design/socket_geometry.py` | Pure G/K/Dual pad, body, courtyard, model, and keycap-envelope definitions |
| `tools/lh60_design/socket_library.py` | Build and apply deterministic Konnect MCP operations for all 21 footprints |
| `tools/lh60_design/layout.py` | Frozen physical keys and four multi-layout region candidates in u coordinates |
| `tools/lh60_design/matrix.py` | 70 logical nodes, 10×7 allocation, GPIO map, shared-socket relationships |
| `tools/lh60_design/project.py` | Create/register production project libraries and apply board rules through MCP |
| `tools/lh60_design/schematic.py` | Deterministically place and connect MCU, switches, diodes, and test pads through MCP |
| `tools/lh60_design/regions.py` | Search/score per-region socket rotations and emit clearance reports |
| `tools/lh60_design/pcb.py` | Deterministic placement, routing, zones, and export orchestration through MCP |
| `tools/lh60_design/mcp.py` | Shared JSON-RPC Konnect client and capability checks |
| `tools/verify_lh60.py` | Read-only production-contract checks and KiCad CLI invocation |
| `lib/lh60-sockets/*.kicad_mod` | 21 generated socket footprints |
| `lib/lh60-mcu/lh60-mcu.kicad_sym` | Audited project-local RP2040-Tiny symbol |
| `lib/lh60-mcu/lh60-mcu.pretty/MCU_RP2040-Tiny_SMD.kicad_mod` | Audited LambdaKB-derived SMD footprint |
| `lib/lh60-mcu/RP2040-Tiny-V1.1.step` | Waveshare official model |
| `lib/lh60-mcu/README.md` | Upstream commit, license, official sources, pin audit |
| `docs/layout-current.md` | Current 15u physical layout and matrix mapping source of truth |
| `docs/regions/*.json` | Machine-readable per-region placements and measured clearances |
| `lh60.kicad_pro/.sch/.pcb` | Blank-origin production project |
| `fp-lib-table`, `sym-lib-table` | Project-local library registrations written by Konnect |

---

### Task 1: Remove the disposable test tree

**Files:**
- Delete: `test/`
- Modify: `docs/current-baseline.md`
- Modify: `docs/socket-baseline.md`
- Modify: `lib/lh60-sockets/README.md`

**Interfaces:**
- Consumes: approved design spec at `docs/superpowers/specs/2026-08-15-lh60-production-v2-design.md`.
- Produces: repository with no tracked `test/` path and no active documentation pointing to committed test boards.

- [ ] **Step 1: Verify the exact deletion set**

Run:

```bash
git ls-files test/ | sort
rg -n 'test/|socket-clean|socket-conflicts|lh60-test' docs lib tools
```

Expected: the tracked disposable projects and every active reference are listed before deletion.

- [ ] **Step 2: Delete the complete tree**

Use `apply_patch` for any text-file removals and `rm` only for generated/binary test artifacts that cannot be represented by the patch tool. Do not delete `tools/update_socket_library.py` yet; Task 3 replaces it after its useful geometry is migrated.

- [ ] **Step 3: Update active documentation**

Replace coupon instructions with:

```text
Production verification creates temporary coupon projects under /tmp through Konnect.
No test KiCad project is committed.
```

Remove claims that `test/socket-clean.kicad_pcb` or `test/socket-conflicts.kicad_pcb` is an active deliverable.

- [ ] **Step 4: Verify deletion**

Run:

```bash
test -z "$(git ls-files test/)"
! rg -n 'test/|socket-clean|socket-conflicts|lh60-test' docs/current-baseline.md docs/socket-baseline.md lib/lh60-sockets/README.md
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit and push**

```bash
git add -A test docs/current-baseline.md docs/socket-baseline.md lib/lh60-sockets/README.md
git commit -m "chore: remove disposable kicad tests" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
git push origin lh60-rp2040-v2
```

---

### Task 2: Extend Konnect for bottom-side footprint construction

**Files (Konnect worktree, not LH60):**
- Modify: `/data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/crates/konnect-core/src/tools/library.rs`
- Test: inline `#[cfg(test)]` module in `/data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/crates/konnect-core/src/tools/library.rs`
- Rebuild/deploy: `/data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/target/release/konnect`

**Interfaces:**
- Consumes: existing `create_footprint` MCP tool.
- Produces: backward-compatible optional pad fields:

```json
{
  "layers": ["B.Cu", "B.Paste", "B.Mask"],
  "rotation": 180.0,
  "roundrect_rratio": 0.2
}
```

`layers` defaults to the existing front-side behavior. `rotation` defaults to `0`. `roundrect_rratio` defaults to the existing value for roundrect pads.

**True blocker:** Task 3 cannot safely create new bottom-side socket footprints until this unit is deployed. This blocker does not prevent Tasks 4–6.

- [ ] **Step 1: Add failing schema and serialization tests**

Add these exact tests next to `create_footprint_emits_courtyard_pin1_and_model`:

```rust
#[test]
fn create_footprint_schema_exposes_pad_layers_rotation_and_roundrect_ratio()

#[tokio::test]
async fn create_footprint_emits_bottom_layer_rotated_roundrect_pad()

#[tokio::test]
async fn create_footprint_legacy_pad_payload_remains_front_side()
```

The bottom-layer test must assert the generated file contains:

```scheme
(at -8.075 4.7 180)
(layers "B.Cu" "B.Paste" "B.Mask")
(roundrect_rratio 0.2)
```

The legacy test must assert an old payload still emits `F.Cu/F.Paste/F.Mask` and no
rotation term.

- [ ] **Step 2: Verify red**

Run:

```bash
cargo test --manifest-path \
  /data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/Cargo.toml \
  -p konnect-core create_footprint_emits_bottom_layer_rotated_roundrect_pad -- --exact
```

Expected: FAIL because `layers`, `rotation`, and `roundrect_rratio` are ignored.

- [ ] **Step 3: Implement optional fields**

Update the input schema and S-expression builder so a supplied bottom-layer pad becomes:

```scheme
(pad "1" smd roundrect
  (at -8.075 4.7 180)
  (size 2.5 2.55)
  (layers "B.Cu" "B.Paste" "B.Mask")
  (roundrect_rratio 0.2))
```

Reject invalid layer names and `roundrect_rratio` outside `0..=0.5`.

- [ ] **Step 4: Run Konnect tests**

Run:

```bash
cargo fmt --manifest-path \
  /data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/Cargo.toml --check
cargo test --manifest-path \
  /data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/Cargo.toml \
  -p konnect-core create_footprint
cargo test --manifest-path \
  /data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/Cargo.toml \
  -p konnect-core
cargo clippy --manifest-path \
  /data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/Cargo.toml \
  -p konnect-core --all-targets -- -D warnings
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit and push Konnect**

Commit in the Konnect integration branch with the required TRAE trailer and push it before deployment.

- [ ] **Step 6: Rebuild and deploy**

Run:

```bash
cargo build --release -p konnect --manifest-path \
  /data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/Cargo.toml
readlink -f ~/.local/bin/konnect
```

Expected symlink target:

```text
/data00/home/wangqiyilang/playground/.worktree/konnect-footprint-graphics/konnect/target/release/konnect
```

The LH60 MCP client starts this deployed binary per operation, so Task 3 does not depend on
restarting the parent session's already-running Konnect process.

- [ ] **Step 7: Verify the deployed tool**

Create `/tmp/lh60-konnect-pad-probe.pretty/probe.kicad_mod` through MCP and assert read-only inspection shows:

```scheme
(layers "B.Cu" "B.Paste" "B.Mask")
(at 0 0 180)
(roundrect_rratio 0.2)
```

---

### Task 3: Generate the 21-footprint socket library

**Files:**
- Create: `tools/lh60_design/__init__.py`
- Create: `tools/lh60_design/mcp.py`
- Create: `tools/lh60_design/socket_geometry.py`
- Create: `tools/lh60_design/socket_library.py`
- Modify: `lib/lh60-sockets/README.md`
- Create/replace through Konnect: `lib/lh60-sockets/*.kicad_mod`
- Delete: `tools/update_socket_library.py`
- Delete: `tools/__init__.py` only if no longer required

**Interfaces:**
- Produces:

```python
U_SIZES = ("1U", "1.25U", "1.5U", "1.75U", "2U", "2.25U", "2.75U")
SERIES = ("Gateron-LP", "Kailh-Choc-V1V2", "Gateron-LP-or-ChocV1")
footprint_names() -> tuple[str, ...]  # exactly 21
build_footprint_specs() -> tuple[FootprintSpec, ...]
apply_socket_library(client: McpClient) -> None
```

- Every spec contains exact pads, `Dwgs.User`, `B.Fab`, `B.CrtYd`, metadata, and models.

- [ ] **Step 1: Write read-only contract tests**

Create focused tests in `tools/verify_lh60.py` that assert:

```python
assert len(footprint_names()) == 21
assert set(pad_numbers) <= {"", "1", "2"}
assert courtyard_clearance_mm >= 0.50
```

G variants use the existing seven-pad Gateron contract. Dual variants use the existing 15-pad Gateron + rotated Choc V1 contract. K variants use the siderakb Choc V1/V2 hybrid source geometry, renumbering electrical contacts to logical `1/2`.

- [ ] **Step 2: Verify red**

Run:

```bash
python -m unittest -v tools.verify_lh60.SocketSpecTest
```

Expected: FAIL because the new modules and 21 inventory do not exist.

- [ ] **Step 3: Implement pure geometry**

Move the Shapely body/terminal/land-pattern functions from `tools/update_socket_library.py`, change courtyard buffer from `0.25` to `0.50`, and add a non-rotated Choc V1/V2 geometry family.

- [ ] **Step 4: Build through Konnect**

For each spec:

1. `create_footprint` with exact pad layers/rotation.
2. `set_footprint_graphics` for `F.SilkS` delete and `Dwgs.User`, `B.Fab`, `B.CrtYd` replace.
3. `set_footprint_metadata` with `exclude_from_pos_files`.
4. `set_footprint_models` with G, K, or both models.

Never copy or text-edit a `.kicad_mod`.

- [ ] **Step 5: Verify inventory and parseability**

Run:

```bash
python -m unittest -v tools.verify_lh60.SocketSpecTest
rm -rf /tmp/lh60-socket-svg
kicad-cli fp export svg --output /tmp/lh60-socket-svg lib/lh60-sockets
test "$(find /tmp/lh60-socket-svg -name '*.svg' | wc -l)" -eq 21
```

- [ ] **Step 6: Generate a temporary clean coupon**

Through Konnect create `/tmp/lh60-socket-coupon.{kicad_pro,kicad_sch,kicad_pcb}`, register `lh60-sockets`, place all 21 footprints with no courtyard overlap, and run DRC.

Expected: 0 errors, 0 warnings, 0 unconnected items.

- [ ] **Step 7: Update documentation**

Document the exact 3×7 inventory, 0.50 mm courtyard, Dual simultaneous-socket coupon requirement, models, hand-solder/PnP behavior, and `/tmp` verification workflow.

- [ ] **Step 8: Commit and push**

```bash
git add tools lib/lh60-sockets
git commit -m "feat(lib): add complete socket families" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
git push origin lh60-rp2040-v2
```

---

### Task 4: Integrate the audited RP2040-Tiny library

**Files:**
- Create through Konnect: `lib/lh60-mcu/lh60-mcu.kicad_sym`
- Create through Konnect: `lib/lh60-mcu/lh60-mcu.pretty/MCU_RP2040-Tiny_SMD.kicad_mod`
- Add: `lib/lh60-mcu/RP2040-Tiny-V1.1.step`
- Add: `lib/lh60-mcu/LICENSE-LambdaKB-MIT.txt`
- Create: `lib/lh60-mcu/README.md`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- Symbol `lh60-mcu:RP2040-Tiny`.
- Footprint `lh60-mcu:MCU_RP2040-Tiny_SMD`.
- Pins:

```text
1..9   GP0..GP8
10..14 GP9..GP13
15..16 GP14..GP15
17..20 GP26..GP29
21     3V3
22     GND
23     VSYS
```

- [ ] **Step 1: Write failing MCU contract tests**

Assert 23 unique symbol pins, pin 23 name `VSYS`, exact SMD pad coordinates from the approved spec, 18 × 23.5 mm body, FPC-side marking, official STEP, and LambdaKB commit `9bb38d7e67c561dfa24428686992abeb17d0a9aa`.

- [ ] **Step 2: Verify red**

Run:

```bash
python -m unittest -v tools.verify_lh60.Rp2040TinyContractTest
```

- [ ] **Step 3: Create symbol through Konnect**

Use `create_symbol` with 20 bidirectional GPIO pins, `3V3`/`VSYS` as `power_in`, and `GND` as `power_in`. Use the exact pin numbers above.

- [ ] **Step 4: Create footprint through Konnect**

Use the audited LambdaKB SMD pad contract:

```text
side pads x = ±8.2 mm at y = 0..20.32 mm
bottom pads y = 20.9 mm at x = +5.08..-5.08 mm
pad size = 2.4 × 1.6 mm
body = 18 × 23.5 mm
courtyard clearance = 0.50 mm
```

Associate the Waveshare official STEP using `set_footprint_models`.

- [ ] **Step 5: Document provenance**

Record Waveshare official schematic/STEP URLs, LambdaKB commit/license, the audited pin map, and why `VSYS` replaces upstream’s inherited `5V` label.

- [ ] **Step 6: Verify and commit**

Run the focused test and KiCad symbol/footprint export, then:

```bash
git add lib/lh60-mcu tools/verify_lh60.py
git commit -m "feat(lib): add audited rp2040 tiny module" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
git push origin lh60-rp2040-v2
```

---

### Task 5: Freeze the current layout and 10×7 matrix

**Files:**
- Create: `tools/lh60_design/layout.py`
- Create: `tools/lh60_design/matrix.py`
- Create: `docs/layout-current.md`
- Modify: `docs/current-baseline.md`
- Modify: `docs/glossary.md`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- Physical origin: top-left of the 15u key field; centers are `(x + width/2, row + 0.5)` u.
- `physical_keys() -> tuple[PhysicalKey, ...]`.
- `logical_nodes() -> tuple[MatrixNode, ...]`, exactly 70.
- `gpio_map() -> MatrixGpioMap`, 10 columns + 7 rows + 3 spare GPIO.

Current physical/shared-node contract:

```text
Row 0: 13 fixed 1u + 2u/split-right shared node + split-left independent node
Row 1: 1.5u + 12 fixed keys + 1.5u
Row 2: 1.75u + 11 fixed keys + 2.25u/split-right shared node + split-left independent node
Row 3: split-left independent + 2.25u/1.25u shared + 10 fixed keys
       + left-1.75u/right-1.75u shared
       + left-Fn/right-Fn physical sockets sharing one logical Fn node
Row 4: 1.25u Ctrl/Win/Alt + 2.25u Space + 1u Fn + four arrows + four 1u right modifiers
```

RShift is treated as the approved standard right-end functional region; no coordinate or rotation is copied from the old test board.

- [ ] **Step 1: Write mapping tests**

Assert:

```python
assert len(logical_nodes()) == 70
assert len({node.logical_node_id for node in logical_nodes()}) == 70
assert len(gpio_map().columns) == 10
assert len(gpio_map().rows) == 7
assert gpio_map().spares == ("GP27", "GP28", "GP29")
assert all(node.row < 7 and node.column < 10 for node in logical_nodes())
```

Also assert all five shared-node groups:

```text
top-right 2u + split-right 1u
ANSI Enter 2.25u + split-right Enter 1.25u
LShift 2.25u + split Shift 1.25u
RShift left 1.75u + right 1.75u
RShift left Fn 1u + RShift right Fn 1u
```

The top-right, Enter, and LShift split-left Fn keys remain independent nodes.

- [ ] **Step 2: Verify red**

Run:

```bash
python -m unittest -v tools.verify_lh60.LayoutMatrixContractTest
```

- [ ] **Step 3: Implement deterministic allocation**

Allocate physical-order nodes row-major into matrix coordinates:

```python
matrix_row, matrix_column = divmod(logical_index, 10)
```

Store the physical key IDs sharing each logical node; do not allocate duplicate nodes for shared sockets.

- [ ] **Step 4: Write current-layout documentation**

Publish all coordinates in u and mm, the 70-node table, the 10×7 map, the GPIO map, and the four unresolved regional rotation sets.

- [ ] **Step 5: Verify and commit**

Run focused tests, `git diff --check`, then commit/push:

```bash
git add tools/lh60_design/layout.py tools/lh60_design/matrix.py tools/verify_lh60.py docs
git commit -m "docs: freeze current production layout" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
git push origin lh60-rp2040-v2
```

---

### Task 6: Create the blank production project and project rules

**Files:**
- Create through Konnect: `lh60.kicad_pro`
- Create through Konnect: `lh60.kicad_sch`
- Create through Konnect: `lh60.kicad_pcb`
- Create through Konnect: `fp-lib-table`
- Create through Konnect: `sym-lib-table`
- Create: `.konnect/project.json`
- Create: `tools/lh60_design/project.py`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- Project nickname registrations:

```text
lh60-sockets -> ${KIPRJMOD}/lib/lh60-sockets
lh60-mcu     -> ${KIPRJMOD}/lib/lh60-mcu/lh60-mcu.pretty
lh60-mcu symbols -> ${KIPRJMOD}/lib/lh60-mcu/lh60-mcu.kicad_sym
```

- [ ] **Step 1: Write failing project tests**

Assert blank-origin project files exist, library registrations are project-relative, and board rules equal the approved values.

- [ ] **Step 2: Verify red**

Run:

```bash
python -m unittest -v tools.verify_lh60.ProjectContractTest
```

- [ ] **Step 3: Create project through Konnect**

Use `create_project(path=<repo>, name="lh60")`, register both footprint libraries and the symbol library, then call `set_design_rules` and `set_layer_constraints`.

- [ ] **Step 4: Set the provisional board envelope**

Create a 285.75 × 95.25 mm key-field outline only as a placement boundary. Do not add margins or mounting holes. The final board edge is adjusted only after all socket and MCU courtyards are placed.

- [ ] **Step 5: Verify and commit**

Use `get_project_info`, `get_design_rules`, `kicad-cli sch upgrade`, and `kicad-cli pcb upgrade` in read/validation mode. Commit/push the blank production skeleton.

---

### Task 7: Build the complete production schematic

**Files:**
- Create: `tools/lh60_design/schematic.py`
- Modify through Konnect: `lh60.kicad_sch`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- 1 MCU, 70 diodes, 75 switch symbols (one per active physical socket), and test-point symbols for `VSYS`, `3V3`, `GND`, `COL0..COL9`, `ROW0..ROW6`, `GP27..GP29`.
- Every switch symbol footprint is assigned from the G/K/Dual selection rule.

**Library gate:** before placement, search the registered KiCad libraries for the actual diode, switch, and test-point symbol/footprint IDs. If system libraries are unavailable, create project-local passive switch/test-point symbols and footprints through Konnect; do not guess library IDs.

- [ ] **Step 1: Write failing schematic contract tests**

Assert:

```python
assert mcu_count == 1
assert diode_count == 70
assert each_logical_node_has_one_diode
assert matrix_nets == {COL0..COL9, ROW0..ROW6}
assert spare_gpio_testpads == {GP27, GP28, GP29}
```

- [ ] **Step 2: Verify red**

Run the focused schematic test before placement.

- [ ] **Step 3: Place components in functional blocks**

Use `batch_place_components` for the matrix blocks and explicit references. Keep each block readable; do not mirror the PCB physical layout in the schematic.

- [ ] **Step 4: Wire COL2ROW**

For every logical node:

```text
COLn -> diode anode
diode cathode -> all shared socket pin 1 instances
all shared socket pin 2 instances -> ROWn
```

Use `batch_connect_to_net` and never guess pin positions.

- [ ] **Step 5: Connect MCU and test pads**

Connect the frozen GPIO map and power/test pads. Mark no unused module power pin as NC; `VSYS`, `3V3`, and `GND` are all exposed to test pads.

- [ ] **Step 6: Verify schematic**

Run:

```text
annotate_schematic
validate_wire_connections
validate_component_connections
find_orphan_items
find_shorted_nets
find_single_pin_nets
run_erc
export_netlist_summary
```

Expected: no unexplained errors; every node and GPIO matches `matrix.py`.

- [ ] **Step 7: Commit and push**

Commit the schematic generator, production schematic, and verification updates.

---

### Task 8: Synchronize PCB from schematic

**Files:**
- Modify through KiCad UI/Konnect IPC: `lh60.kicad_pcb`

**Interfaces:**
- Consumes the verified schematic.
- Produces all schematic footprints and nets on the PCB with reference/value/footprint fields intact.

**True blocker:** KiCad 10 removed CLI PCB sync. This task requires KiCad UI **Tools → Update PCB from Schematic**.

- [ ] **Step 1: Launch KiCad through Konnect**

Call `launch_kicad_ui(project=<repo>/lh60.kicad_pro)` and verify `check_kicad_ui`.

- [ ] **Step 2: Run Update PCB from Schematic**

Use KiCad UI **Tools → Update PCB from Schematic**, review zero missing-footprint errors, apply changes, and save. If the environment has no display/IPC, stop only this and dependent PCB tasks and ask the user to open the project and perform the menu action.

- [ ] **Step 3: Verify synchronization**

Use `get_component_list`, `get_nets_list`, and `validate_for_manufacturing`. Expected footprint counts match the schematic and the board no longer reports “No footprints found”.

- [ ] **Step 4: Commit and push**

Commit only the synchronized PCB change with the required trailer.

---

### Task 9: Solve the four multi-layout regions independently

**Files:**
- Create: `tools/lh60_design/regions.py`
- Create through Konnect: `/tmp/lh60-region-<name>.kicad_*`
- Create: `docs/regions/top-right.json`
- Create: `docs/regions/enter.json`
- Create: `docs/regions/lshift.json`
- Create: `docs/regions/rshift.json`
- Modify through Konnect IPC: `lh60.kicad_pcb`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- `solve_region(region: RegionSpec) -> RegionReport`.
- Search rotations in `{0, 90, 180, 270}` for all single-G sockets from blank regional geometry.
- Hard checks:

```text
copper clearance >= 0.25 mm
independent component-hole edge clearance >= 0.45 mm
target hole edge clearance >= 0.50 mm
courtyard clearance >= 0.00 mm after each footprint's 0.50 mm buffer
```

- [ ] **Step 1: Write solver tests**

Test deterministic ordering, rotation enumeration, exact report fields, and failure reporting with `actual`, `required`, and `shortfall`.

- [ ] **Step 2: Verify red**

Run the region-solver test class.

- [ ] **Step 3: Solve single-G regions**

For each region, generate a temporary coupon through Konnect, place every mutually exclusive socket simultaneously, run DRC, and compute geometry independently.

- [ ] **Step 4: Attempt Dual upgrades**

Replace one candidate at a time with the matching Dual footprint. Keep the upgrade only if all checks still pass.

- [ ] **Step 5: Handle an unsolved region**

If no assignment passes, write the JSON report and present the smallest shortfall/alternatives to the user. Do not block other region tasks.

- [ ] **Step 6: Apply solved placements**

Move/rotate the corresponding PCB footprints through IPC and verify each placement immediately.

- [ ] **Step 7: Commit each region separately**

Use one commit and push per region:

```text
feat(pcb): solve top-right layout
feat(pcb): solve enter layout
feat(pcb): solve left-shift layout
feat(pcb): solve right-shift layout
```

---

### Task 10: Place the remaining PCB

**Files:**
- Create: `tools/lh60_design/pcb.py`
- Modify through Konnect IPC: `lh60.kicad_pcb`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- Fixed keys use Dual footprints.
- RP2040-Tiny is bottom-side under the 2.25u space area, horizontal, FPC facing the rear edge unless courtyard checks require a translated position.
- Diodes and test pads remain bottom-side and accessible.

- [ ] **Step 1: Place fixed sockets**

Convert each physical key center from u to mm at 19.05 mm pitch and place all non-region footprints. Verify the 15u field extents.

- [ ] **Step 2: Place MCU**

Enumerate MCU candidates on a 0.50 mm grid in this order:

1. inside the 2.25u space-key envelope, rotated 90°, FPC toward the rear edge;
2. across the complete bottom-row envelope, rotated 90°, FPC toward the rear edge;
3. in a rear board extension no deeper than 20.0 mm.

Reject candidates that overlap any socket/diode courtyard or violate 0.50 mm copper-to-edge.
Choose the surviving candidate with the smallest board-area increase, then shortest total Manhattan
distance to the 17 matrix GPIO trunks. If no candidate survives, stop MCU placement and report the
minimum required board extension; do not overlap components.

- [ ] **Step 3: Place diodes and test pads**

Place one diode per logical node close to its socket group. Arrange matrix and spare-GPIO test pads in compact labeled banks.

- [ ] **Step 4: Finalize board outline**

Set the smallest rectangular/rounded outline that preserves at least 0.50 mm copper-to-edge and all component courtyards. Do not add mounting holes.

- [ ] **Step 5: Verify placement**

Run component-overlap, edge-clearance, board-extents, and regional-report checks before routing.

- [ ] **Step 6: Commit and push**

Commit the placement and outline as an independently reviewable unit.

---

### Task 11: Route the PCB and add ground zones

**Files:**
- Modify through Konnect IPC: `lh60.kicad_pcb`
- Modify: `tools/lh60_design/pcb.py`
- Modify: `tools/verify_lh60.py`

**Interfaces:**
- Signal class: 0.25 mm width/clearance.
- Power class: at least 0.50 mm width.
- Via: 0.30/0.70 mm.

- [ ] **Step 1: Create and assign netclasses**

Create `Signal`, `Power`, and `Matrix` classes and assign `VSYS/3V3/GND`, row/column nets, and local node nets.

- [ ] **Step 2: Route MCU and matrix trunks**

Route row/column trunks first, then diode-to-switch node branches. Keep every independent hole edge and board edge rule.

- [ ] **Step 3: Route test pads and power**

Route power with ≥0.50 mm width. Keep test pads probe-accessible.

- [ ] **Step 4: Route remaining ratsnest**

Use `get_nets_list`, `get_component_pads`, `route_pad_to_pad`, and `route_trace`; never route by guessed coordinates.

- [ ] **Step 5: Add and refill GND zones**

Add GND zones on F.Cu and B.Cu, then call `refill_zones`. If IPC is unavailable, restore it rather than accepting stale zones.

- [ ] **Step 6: Run DRC and fix only design-related violations**

Run `run_drc`; resolve every short, unrouted item, clearance, hole, courtyard, edge, and zone violation. Do not waive violations to finish.

- [ ] **Step 7: Commit and push**

Commit the fully routed board after a fresh zero-error DRC.

---

### Task 12: Final manufacturing verification and export

**Files:**
- Create: `FabOutput/` locally (ignored)
- Modify: `docs/current-baseline.md`
- Modify: `docs/layout-current.md`
- Modify: `tools/verify_lh60.py`
- No KiCad source change unless verification finds a defect

**Interfaces:**
- Produces Gerber, drill, BOM, and diode position files for JLCPCB.
- Produces a final review report and current board dimensions for live JLC pricing.

- [ ] **Step 1: Run the complete software verification**

Run:

```bash
python -m unittest -v tools.verify_lh60
git diff --check
```

- [ ] **Step 2: Run fresh KiCad checks**

Call:

```text
run_erc
run_drc
run_design_review
validate_for_manufacturing(fab_house="JLCPCB")
```

Any `partial` or `failed` review status is `INCOMPLETE` and blocks production approval.

- [ ] **Step 3: Export manufacturing package**

Use `export_manufacturing_package`, then independently export/check Gerbers, drill files, BOM, and bottom-side position file. Socket and RP2040-Tiny references must be absent from PnP; all 70 diodes must be present.

- [ ] **Step 4: Verify files and board dimensions**

Record final width/height and submit those exact dimensions to JLC live pricing. Do not claim a fixed 50-yuan price from static rules.

- [ ] **Step 5: Document residual physical gates**

Record that production approval still requires a fabricated Dual coupon with both sockets soldered and both switch families inserted/removed successfully.

- [ ] **Step 6: Commit and push final documentation**

Commit the verified baseline/docs/tool changes with the required trailer and push.

- [ ] **Step 7: Verify delivery history**

Run:

```bash
git status --short --branch
git log --oneline --decorate origin/master..HEAD
test "$(git rev-parse HEAD)" = "$(git ls-remote origin refs/heads/lh60-rp2040-v2 | awk '{print $1}')"
```

Expected: clean worktree and local/remote HEAD equality.
