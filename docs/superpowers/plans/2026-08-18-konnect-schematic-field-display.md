# Konnect Schematic Field Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe atomic Reference/Value visibility edits and reproducible symbol-field anchors needed by the LH60 A3 schematic.

**Architecture:** A new `sch_batch` tool validates every visibility edit from one source snapshot, changes only direct property-level `(hide yes)` nodes, and performs at most one revision-checked write. Independently, `create_symbol` gains optional Reference/Value anchor objects while retaining its existing automatic placement as the compatibility default; the two implementations have disjoint write scopes and converge before protocol tests and deployment.

**Tech Stack:** Rust 1.96, Konnect 0.6.1, MCP JSON Schema, `konnect-sexp` byte edits, stdio protocol tests.

## Global Constraints

- Root `/data00/home/wangqiyilang/playground/konnect` stays clean on `main`; the integration worktree is `/data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect`.
- Base on reviewed `upstream/main`, currently `3827cddac16207e6104575b1107e169d98878d76`; inspect any fast-forward before creating branches.
- Public visibility tool name and fields are frozen: `batch_set_schematic_field_visibility`, `reference_visible`, and `value_visible`.
- Public anchor fields are frozen as optional `reference_at` and `value_at` objects with required numeric `x`/`y` and optional numeric `rotation`; omission preserves current automatic placement.
- Visibility validation is all-or-nothing. Missing components/properties, duplicate references, malformed edits, unknown keys, or revision conflicts write nothing.
- Visibility edits preserve field text, positions, effects/style, UUIDs, symbol identity, and all unrelated nodes.
- A repeated visibility request is a successful byte-identical no-op.
- Update bundled skills and all registered-tool counts in the same delivery.
- Every logical unit is independently verified, committed, and pushed before the next unit begins.
- Every commit ends with exactly one `Co-authored-by: TRAE CLI <noreply@bytedance.com>`. Use a temporary empty `core.hooksPath` because the configured hook adds a second, nonconforming trailer.

## File Map and Write Scopes

| Unit | Exclusive files |
|---|---|
| K1 visibility | `crates/konnect-core/src/tools/sch_batch.rs`, `crates/konnect-core/src/router/registry.rs` |
| K2 anchors | `crates/konnect-core/src/tools/library.rs` |
| K3 query identity/inventory | `crates/konnect-core/src/tools/sch_analysis.rs`, `crates/konnect-core/src/tools/pcb_board.rs` |
| K4 public contract | `README.md`, `DEV.md`, `tool-directory.md`, bundled schematic/library skills, `crates/konnect/tests/asset_references.rs` |
| K5 protocol/deploy | `crates/konnect/tests/protocol_stdio.rs` |

K1, K2, and K3 may run in parallel because their files are disjoint and their public interfaces are frozen above. K4 is blocked on those interfaces being real, and K5 is blocked on the integrated handlers and response schema being executable.

## Dependency Graph

```text
K0 integration worktree
├── K1 visibility tool + unit tests + registry count
├── K2 create_symbol field anchors + unit tests
└── K3 stable label UUID + board zone count queries + unit tests
          \       |       /
           K4 docs + bundled skills + count guards
                         |
           K5 stdio + full gates + reversible deployment
```

---

### Task K0: Establish the Konnect Integration Worktree

**Files:** No tracked changes.

**Interfaces:**
- Consumes: clean root and `upstream/main`.
- Produces: integration branch `feat/schematic-field-display`.

- [ ] **Step 1: Verify and fetch the root**

```bash
git -C /data00/home/wangqiyilang/playground/konnect status --short --branch
git -C /data00/home/wangqiyilang/playground/konnect fetch upstream origin
git -C /data00/home/wangqiyilang/playground/konnect log --oneline \
  3827cddac16207e6104575b1107e169d98878d76..upstream/main
```

Expected: clean root. If the log is nonempty, review it and use the verified `upstream/main` successor.

- [ ] **Step 2: Create the integration worktree**

```bash
git -C /data00/home/wangqiyilang/playground/konnect worktree add \
  -b feat/schematic-field-display \
  /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect \
  upstream/main
```

- [ ] **Step 3: Prove the baseline**

```bash
cd /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect
cargo test -p konnect-core sch_batch --locked
cargo test -p konnect-core create_symbol --locked
```

Expected: both focused baselines pass.

---

### Task K1: Atomic Placed-Field Visibility

**Files:**
- Modify: `crates/konnect-core/src/tools/sch_batch.rs`
- Modify: `crates/konnect-core/src/router/registry.rs`

**Interfaces:**
- Consumes: `find_all_symbol_instance_blocks`, `find_direct_child_blocks`, `SexpEdit`, `apply_edits`, `read_consistent`, `write_atomic_if_unchanged`.
- Produces: frozen `batch_set_schematic_field_visibility(schematic, edits)` contract.

- [ ] **Step 1: Create the isolated K1 worktree**

```bash
git -C /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect worktree add \
  -b task/schematic-field-visibility \
  /data00/home/wangqiyilang/playground/.worktree/schematic-field-visibility/konnect \
  feat/schematic-field-display
```

- [ ] **Step 2: Add failing schema and behavior tests**

Add `mod field_visibility_tests` beside existing `sch_batch` tests. The happy path must exercise:

```rust
let result = handle_batch_set_schematic_field_visibility(
    &json!({
        "schematic": path,
        "edits": [{
            "reference": "R1",
            "reference_visible": false,
            "value_visible": true
        }]
    }),
    &test_ctx(),
).await.unwrap();
assert!(!result.is_error);
```

Also cover only-one-field edits, multi-unit references, byte-identical no-op, empty edits, wrong types, unknown keys, duplicate request references, missing symbol/property, duplicate/malformed hide nodes, mixed valid+invalid zero-write, and stale-source structured conflict.

- [ ] **Step 3: Run RED**

```bash
cargo test -p konnect-core field_visibility_tests --locked
```

Expected: compile failure because the handler is absent.

- [ ] **Step 4: Register the exact schema**

Add to `sch_batch::tools()`:

```json
{
  "type": "object",
  "properties": {
    "schematic": {"type": "string"},
    "edits": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "reference": {"type": "string"},
          "reference_visible": {"type": "boolean"},
          "value_visible": {"type": "boolean"}
        },
        "required": ["reference"],
        "additionalProperties": false
      }
    }
  },
  "required": ["schematic", "edits"]
}
```

Update `sch_batch.tool_count` from 12 to 13.

- [ ] **Step 5: Implement typed prevalidation and byte edits**

Use internal requests:

```rust
struct FieldVisibilityRequest {
    reference: String,
    reference_visible: Option<bool>,
    value_visible: Option<bool>,
}

struct VisibilityTransition { old: bool, new: bool }
```

Validate all items before building edits. For hidden state, insert direct `(hide yes)` before direct `(effects ...)` with matching indentation, or immediately before the property closing parenthesis when a valid property has no effects. For visible state, delete only that direct hide node and its local whitespace. Add a unit case for a property without effects. If output equals input, skip persistence. Map `SexpError::Conflict` to `ToolErrorKind::Conflict`. Return `updated_count`, `unchanged_count`, and only requested fields as `{"old":...,"new":...}`.

- [ ] **Step 6: Run GREEN and format**

```bash
cargo test -p konnect-core field_visibility_tests --locked
cargo test -p konnect-core router --locked
cargo fmt --all -- --check
```

- [ ] **Step 7: Commit and push K1**

```bash
git add crates/konnect-core/src/tools/sch_batch.rs \
  crates/konnect-core/src/router/registry.rs
empty_hooks=$(mktemp -d /tmp/konnect-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(schematic): add atomic field visibility edits" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/schematic-field-visibility
```

---

### Task K2: Reproducible Symbol Field Anchors

**Files:**
- Modify: `crates/konnect-core/src/tools/library.rs`

**Interfaces:**
- Consumes: existing `create_symbol`.
- Produces: optional `reference_at` and `value_at` objects; omitted values preserve automatic anchors.

- [ ] **Step 1: Create K2 from the frozen integration base**

```bash
git -C /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect worktree add \
  -b task/symbol-field-anchors \
  /data00/home/wangqiyilang/playground/.worktree/symbol-field-anchors/konnect \
  feat/schematic-field-display
```

- [ ] **Step 2: Add RED tests**

Test schema, explicit anchors, partial override, invalid/missing numeric coordinates, and legacy byte-equivalent automatic anchors. Use this input:

```json
{
  "reference_at": {"x": 0, "y": 17.78, "rotation": 0},
  "value_at": {"x": 0, "y": -20.32, "rotation": 0}
}
```

Run `cargo test -p konnect-core symbol_field_anchor --locked` and confirm RED.

- [ ] **Step 3: Extend schema and generation**

Add both optional objects with `additionalProperties=false`. Parse strictly through a helper returning `(x, y, rotation)`, defaulting rotation to 0. Feed explicit coordinates to `visible_property`; when absent, retain `(max_y + 2.54)` and `(min_y - 2.54)` exactly.

- [ ] **Step 4: Run GREEN**

```bash
cargo test -p konnect-core symbol_field_anchor --locked
cargo test -p konnect-core create_symbol --locked
cargo fmt --all -- --check
```

- [ ] **Step 5: Commit and push K2**

Use the same temporary empty-hooks pattern:

```bash
git add crates/konnect-core/src/tools/library.rs
empty_hooks=$(mktemp -d /tmp/konnect-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(library): support explicit symbol field anchors" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/symbol-field-anchors
```

---

### Task K3: Expose Stable Label UUIDs and Board Zone Inventory

**Files:**
- Modify: `crates/konnect-core/src/tools/sch_analysis.rs`
- Modify: `crates/konnect-core/src/tools/pcb_board.rs`

**Interfaces:**
- Consumes: existing typed `Label`, `GlobalLabel`, and `HierarchicalLabel` UUID fields.
- Produces: existing `list_schematic_labels` response with an additional nonempty `uuid` field on every label item, and existing `get_board_info` response with `zone_count`; both are backward-compatible response enrichments.

- [ ] **Step 1: Create the isolated K3 worktree**

```bash
git -C /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect worktree add \
  -b task/schematic-label-uuids \
  /data00/home/wangqiyilang/playground/.worktree/schematic-label-uuids/konnect \
  feat/schematic-field-display
```

- [ ] **Step 2: Add a RED response test**

Create a fixture containing one net, global, and hierarchical label with known UUIDs. Call `handle_list_labels` and assert every returned item includes the exact UUID. Also assert duplicate same-net/same-position labels remain distinguishable by UUID. Add a real KiCad-style board fixture with two top-level `(zone ...)` blocks and assert `handle_get_board_info` returns `zone_count: 2`; the blank fixture must return zero.

Run:

```bash
cargo test -p konnect-core query_identity_inventory --locked
```

Expected: RED because the handler currently omits UUIDs.

- [ ] **Step 3: Return typed UUIDs without changing existing fields**

Extend each JSON object in `handle_list_labels` with `"uuid": l.uuid` (or the corresponding global/hierarchical value). Do not rename `net`, `type`, `x`, `y`, or `rotation`. A parsed empty UUID is an error result rather than an unusable delete identity. In `handle_get_board_info`, compute `let zone_count = tree.find_all("zone").len();` and add that number without changing existing fields.

- [ ] **Step 4: Run GREEN, commit, and push K3**

```bash
cargo test -p konnect-core query_identity_inventory --locked
git add crates/konnect-core/src/tools/sch_analysis.rs \
  crates/konnect-core/src/tools/pcb_board.rs
empty_hooks=$(mktemp -d /tmp/konnect-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "feat(queries): expose stable design inventory" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/schematic-label-uuids
```

---

### Task K4: Integrate Core Units and Publish the Contract

**Files:**
- Modify: `README.md`
- Modify: `DEV.md`
- Modify: `tool-directory.md`
- Modify: `crates/konnect/assets/skills/kicad-schematic/SKILL.md`
- Modify: `crates/konnect/assets/skills/kicad-library/SKILL.md`
- Modify: `crates/konnect/tests/asset_references.rs`

**Interfaces:**
- Consumes: K1, K2, and K3 task HEADs.
- Produces: integrated public API and count-consistent docs.

- [ ] **Step 1: Integrate K1, K2, and K3 by exact branch HEAD**

```bash
cd /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/.worktree/schematic-field-visibility/konnect rev-parse HEAD)"
cargo test -p konnect-core field_visibility_tests --locked
git push -u origin feat/schematic-field-display

git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/.worktree/symbol-field-anchors/konnect rev-parse HEAD)"
cargo test -p konnect-core symbol_field_anchor --locked
git push origin feat/schematic-field-display

git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/.worktree/schematic-label-uuids/konnect rev-parse HEAD)"
cargo test -p konnect-core query_identity_inventory --locked
git push origin feat/schematic-field-display
```

- [ ] **Step 2: Create the K4 documentation worktree from the updated integration branch**

```bash
git -C /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect worktree add \
  -b task/schematic-field-display-docs \
  /data00/home/wangqiyilang/playground/.worktree/schematic-field-display-docs/konnect \
  feat/schematic-field-display
cd /data00/home/wangqiyilang/playground/.worktree/schematic-field-display-docs/konnect
```

- [ ] **Step 3: Update counts and tool directory**

Apply exact count changes: README 203→204; DEV `sch_batch` 12→13, registered 203→204, full catalogue 209→210; tool-directory registered 203→204, total 209→210, and `sch_batch` 12→13. Add the new tool row.

- [ ] **Step 4: Update both bundled skills**

Document atomic visibility use and prohibit blanking fields in `kicad-schematic`. Document `reference_at`/`value_at` and their automatic defaults in `kicad-library`.

- [ ] **Step 5: Run docs guards**

```bash
cargo test -p konnect --test doc_tool_counts --locked
cargo test -p konnect --test asset_references --locked
```

Add exactly `reference_visible`, `value_visible`, `reference_at`, and `value_at` to `NOT_TOOLS`, with a comment that they are nested public schema fields rather than tool names. The asset test must pass with those explicit classifications.

- [ ] **Step 6: Commit and push K4**

```bash
git add README.md DEV.md tool-directory.md crates/konnect/assets/skills \
  crates/konnect/tests/asset_references.rs
empty_hooks=$(mktemp -d /tmp/konnect-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "docs(schematic): publish field display controls" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/schematic-field-display-docs
```

- [ ] **Step 7: Integrate K4 into the integration branch**

```bash
cd /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/.worktree/schematic-field-display-docs/konnect rev-parse HEAD)"
cargo test -p konnect --test doc_tool_counts --locked
cargo test -p konnect --test asset_references --locked
git push origin feat/schematic-field-display
```

---

### Task K5: Real Protocol Proof, Full Gates, and Local Deployment

**Files:**
- Modify: `crates/konnect/tests/protocol_stdio.rs`

**Interfaces:**
- Consumes: integrated K1-K4.
- Produces: real-binary proof and deployed 0.6.1 schema for LH60.

- [ ] **Step 1: Create the K5 protocol worktree**

```bash
git -C /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect worktree add \
  -b task/schematic-field-display-protocol \
  /data00/home/wangqiyilang/playground/.worktree/schematic-field-display-protocol/konnect \
  feat/schematic-field-display
cd /data00/home/wangqiyilang/playground/.worktree/schematic-field-display-protocol/konnect
```

- [ ] **Step 2: Add real-binary stdio coverage**

Add `schematic_field_display_round_trips_over_stdio`. Start the real binary, load `sch_batch`, `sch_analysis`, `pcb_board`, and `library`, copy `crates/konnect-core/tests/fixtures/test.kicad_sch` and `test.kicad_pcb` into one temporary directory, mutate only those copies, verify old/new visibility, verify byte-identical repeat, verify explicit symbol anchors in a temporary library, verify `list_schematic_labels` returns stable UUIDs for duplicate-position labels, verify `get_board_info.zone_count`, and verify missing `edits` returns `invalid_argument`.

- [ ] **Step 3: Run GREEN against the integrated source**

```bash
cargo test -p konnect --test protocol_stdio \
  schematic_field_display_round_trips_over_stdio --locked
```

- [ ] **Step 4: Commit and push K5**

```bash
git add crates/konnect/tests/protocol_stdio.rs
empty_hooks=$(mktemp -d /tmp/konnect-empty-hooks.XXXXXX)
git -c core.hooksPath="$empty_hooks" commit \
  -m "test(schematic): cover field display controls over stdio" \
  -m "Co-authored-by: TRAE CLI <noreply@bytedance.com>"
rmdir "$empty_hooks"
git push -u origin task/schematic-field-display-protocol
```

- [ ] **Step 5: Integrate K5, then run all release gates and build in integration**

```bash
cd /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect
git cherry-pick "$(git -C /data00/home/wangqiyilang/playground/.worktree/schematic-field-display-protocol/konnect rev-parse HEAD)"
cargo test -p konnect --test protocol_stdio \
  schematic_field_display_round_trips_over_stdio --locked
git push origin feat/schematic-field-display
```

```bash
cargo test --workspace --locked --lib --tests
cargo test --workspace --locked --doc
cargo clippy --workspace --locked --all-targets -- -D warnings
cargo fmt --all -- --check
cargo build --release --locked -p konnect
git diff --check
git status --short --branch
```

Expected: all pass and worktree clean.

- [ ] **Step 6: Deploy reversibly and refresh shared skills**

```bash
readlink -f /data00/home/wangqiyilang/.local/bin/konnect \
  > /tmp/konnect-before-field-display.txt
ln -sfn \
  /data00/home/wangqiyilang/playground/.worktree/debug-connectors-layout/konnect/target/release/konnect \
  /data00/home/wangqiyilang/.local/bin/konnect
/data00/home/wangqiyilang/.local/bin/konnect init --client codex
/data00/home/wangqiyilang/.local/bin/konnect --version
```

Expected version: 0.6.1. Roll back with:

```bash
ln -sfn "$(sed -n '1p' /tmp/konnect-before-field-display.txt)" \
  /data00/home/wangqiyilang/.local/bin/konnect
```

- [ ] **Step 7: Verify fresh deployed schemas**

From LH60's `McpClient` in a fresh process, assert:

```python
assert "batch_set_schematic_field_visibility" in client.tool_schemas("sch_batch")
library = client.tool_schemas("library")
assert "reference_at" in library["create_symbol"]["properties"]
assert "value_at" in library["create_symbol"]["properties"]
assert "flip_component" in client.tool_schemas("pcb_components")
board_info = client.tool_schemas("pcb_board")["get_board_info"]
assert board_info is not None
```

Call `get_board_info` on a temporary board and require the response to include `zone_count`; schema presence alone cannot express response fields.

Inspect live processes without a PID placeholder:

```bash
for proc_link in /proc/[0-9]*/exe; do
  exe_target=$(readlink "$proc_link" 2>/dev/null) || continue
  case "$exe_target" in
    *konnect*) print -r -- "$proc_link -> $exe_target" ;;
  esac
done
```

Restart every Konnect process whose target ends in `(deleted)` before any production KiCad write.

- [ ] **Step 8: Review and hand off the blocking SHA**

Review `upstream/main..feat/schematic-field-display`, confirm five independently revertible commits, push the integration branch, and record `git rev-parse HEAD` in the LH60 execution log as the tool capability gate.
