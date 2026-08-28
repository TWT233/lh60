# LH60 RP2040 V2 Parallel Implementation Handoff

## 1. Objective

从当前 `lh60-rp2040-v2` 集成分支继续完成生产工程。当前配列不再等待新 KLE，按已批准的
15u × 5 行、19.05 mm 键距、方向键底排、无 ISO、四个多配列区域继续。

本 handoff 的目标不是让多个 agent 同时编辑一个工作树，而是把剩余工作拆成：

- 独立分支；
- 独立 worktree；
- 互斥 write scope；
- 独立提交；
- 主协调者按依赖顺序 cherry-pick。

## 2. Authoritative Inputs

按优先级：

1. `docs/superpowers/specs/2026-08-15-lh60-production-v2-design.md`
2. `docs/superpowers/plans/2026-08-15-lh60-production-v2.md`
3. `docs/current-baseline.md`
4. `docs/socket-baseline.md`
5. 本 handoff

如果它们冲突：

- 产品和制造要求以 design spec 为准；
- 任务边界、命令和提交序列以 implementation plan 为准；
- 本 handoff 只补充当前进度、并行拓扑和 agent 交接方式。

## 3. Non-negotiable Rules

- 最终集成分支：`lh60-rp2040-v2`。
- 根仓库 `master` 保持干净。
- 每个 agent 使用独立的 `.worktree/<task-slug>/lh60/`。
- 每个 agent 只能修改自己的 write scope。
- KiCad protected files 不得直接文本编辑：
  - `*.kicad_pro`
  - `*.kicad_sch`
  - `*.kicad_pcb`
  - `*.kicad_sym`
  - `*.kicad_mod`
  - `fp-lib-table`
  - `sym-lib-table`
- 上述文件的写入全部通过 Konnect MCP。
- 每个提交消息最后必须且只能出现一次：

```text
Co-authored-by: TRAE CLI <noreply@bytedance.com>
```

- Agent 完成后必须：
  1. 运行任务自己的验收命令；
  2. 提交；
  3. 推送自己的任务分支；
  4. 返回 commit SHA、修改文件和测试证据。
- Agent 不得：
  - 合并/重置/强推集成分支；
  - 修改其他 agent 文件；
  - stash 或 reset 覆盖别人的工作；
  - 把测试板、旧生产板坐标或旧 DRC 结论复制到生产工程。

## 4. Current Snapshot

### 4.1 LH60 integration branch

```text
branch: lh60-rp2040-v2
HEAD:   63a3072ba9f8ad063f86f7e543b49cf2b50fba74
remote: origin/lh60-rp2040-v2 at the same SHA
```

Recent committed units:

| Commit | Deliverable |
|---|---|
| `1623448` | Approved production design specification |
| `0020c95` | Complete implementation plan |
| `3bfa068` | Deleted the complete `test/` tree |
| `63a3072` | Generated and verified 21 G/K/Dual socket footprints |

### 4.2 Socket library status

- 3 series × 7 U sizes = 21 footprints.
- `B.CrtYd` clearance: 0.50 mm.
- Deployed Konnect capability check passes.
- Current software verification:

```text
16 socket tests passed
21 footprint SVG exports passed
/tmp clean coupon:
  0 violations
  0 unconnected items
```

Relevant files:

```text
lib/lh60-sockets/
tools/lh60_design/socket_geometry.py
tools/lh60_design/socket_library.py
tools/lh60_design/mcp.py
tools/verify_lh60.py
```

### 4.3 Konnect dependency

Konnect branch:

```text
repo:   TWT233/Konnect
branch: feat/footprint-graphics
HEAD:   7b120692f61053b892a921751c059673b760b879
```

Upstream PR:

```text
https://github.com/mixelpixx/Konnect/pull/205
state: open
draft: false
mergeable_state: clean
CI: 7/7 passing
```

The deployed binary already includes the needed bottom-side pad support:

```text
create_footprint pads:
  layers
  rotation
  roundrect_rratio
```

LH60 work does not need to wait for PR #205 to merge because the local deployed binary is verified.

### 4.4 Seeded MCU WIP

The MCU WIP has been moved to the isolated Agent A worktree:

```text
/data00/home/wangqiyilang/playground/lh60/.worktree/rp2040-tiny-lib/lh60
branch: task/rp2040-tiny-lib
base:   63a3072ba9f8ad063f86f7e543b49cf2b50fba74
```

Agent A status:

```text
M  tools/verify_lh60.py
?? tools/lh60_design/mcu_library.py
?? lib/lh60-mcu/LICENSE-LambdaKB-MIT.txt
?? lib/lh60-mcu/RP2040-Tiny-V1.1.step
```

Current test state:

```text
PASS:
  Rp2040TinyContractTest.test_symbol_contract_has_23_unique_official_pins
  Rp2040TinyContractTest.test_footprint_contract_matches_lambdakb_smd_coordinates

EXPECTED RED:
  Rp2040TinyContractTest.test_generated_library_contains_symbol_footprint_model_and_provenance

Reason:
  lib/lh60-mcu/lh60-mcu.kicad_sym does not exist yet
```

The WIP is not committed. It belongs only to Agent A and is not present in the integration worktree.

The following bootstrap has already been executed; it is retained only as recovery documentation:

```bash
root=/data00/home/wangqiyilang/playground/lh60
integration=$root/.worktree/lh60-rp2040-v2/lh60
agent_a=$root/.worktree/rp2040-tiny-lib/lh60

git -C "$root" worktree add \
  -b task/rp2040-tiny-lib \
  "$agent_a" \
  63a3072ba9f8ad063f86f7e543b49cf2b50fba74

mkdir -p "$agent_a/tools/lh60_design" "$agent_a/lib/lh60-mcu"
cp "$integration/tools/verify_lh60.py" "$agent_a/tools/verify_lh60.py"
cp "$integration/tools/lh60_design/mcu_library.py" \
  "$agent_a/tools/lh60_design/mcu_library.py"
cp -a "$integration/lib/lh60-mcu/." "$agent_a/lib/lh60-mcu/"

git -C "$agent_a" status --short
```

Expected Agent A status:

```text
M  tools/verify_lh60.py
?? tools/lh60_design/mcu_library.py
?? lib/lh60-mcu/LICENSE-LambdaKB-MIT.txt
?? lib/lh60-mcu/RP2040-Tiny-V1.1.step
```

The copies were verified byte-for-byte with SHA-256 before the integration worktree was restored.
Current integration status before committing this handoff:

```text
?? docs/handoff/
```

### 4.5 Prepared parallel worktrees

All Wave 1 worktrees already exist locally:

| Agent | Branch | Worktree |
|---|---|---|
| A | `task/rp2040-tiny-lib` | `.worktree/rp2040-tiny-lib/lh60` |
| B | `task/layout-matrix` | `.worktree/layout-matrix/lh60` |
| C | `task/project-skeleton` | `.worktree/project-skeleton/lh60` |
| D | `task/region-solver` | `.worktree/region-solver/lh60` |

Each is based on `63a3072ba9f8ad063f86f7e543b49cf2b50fba74`. These branches are local
until their agents finish, commit, and push.

## 5. Shared Contracts

### 5.1 Socket library

```text
nickname: lh60-sockets
series:
  Gateron-LP-Hotswap-Socket-{U}
  Kailh-Choc-V1V2-Hotswap-Socket-{U}
  Gateron-LP-or-ChocV1-Hotswap-Socket-{U}
sizes:
  1U, 1.25U, 1.5U, 1.75U, 2U, 2.25U, 2.75U
logical pads:
  1, 2
```

### 5.2 RP2040-Tiny

```text
symbol:    lh60-mcu:RP2040-Tiny
footprint: lh60-mcu:MCU_RP2040-Tiny_SMD
pin map:
  1..9   GP0..GP8
  10..14 GP9..GP13
  15     GP14
  16     GP15
  17     GP26
  18     GP27
  19     GP28
  20     GP29
  21     3V3
  22     GND
  23     VSYS
```

No `5V`, SWD, RUN, BOOTSEL, or USB data pins exist on the carrier-board symbol.

### 5.3 Matrix

```text
logical nodes: 70
physical socket symbols: 75
matrix: 10 columns × 7 rows
COL0..COL9: GP0..GP9
ROW0..ROW6: GP10..GP15, GP26
spare GPIO: GP27, GP28, GP29
diode: 1N4148WS / SOD-323
direction: COL2ROW
```

Five shared logical-node groups:

1. top-right `2u` + split-right `1u`
2. ANSI Enter `2.25u` + split-right Enter `1.25u`
3. LShift `2.25u` + split Shift `1.25u`
4. RShift left `1.75u` + right `1.75u`
5. RShift left Fn `1u` + RShift right Fn `1u`

`r3_rshift_2.75u` / `SW59` was retired after this parallel handoff was first
issued. Active references remain stable as `SW1..SW58, SW60..SW76`.

Independent split-left Fn nodes:

- top-right split-left Fn
- Enter split-left Fn
- LShift split-left Fn

### 5.4 PCB rules

```text
signal width:             0.25 mm
copper clearance:         0.25 mm
power width:              >= 0.50 mm
via drill/diameter:       0.30 / 0.70 mm
copper to CNC edge:       >= 0.50 mm
hole edge target:         >= 0.50 mm
hole edge hard minimum:   >= 0.45 mm
```

## 6. Parallel DAG

```text
Wave 1
├── A: RP2040-Tiny library
├── B: layout + 10×7 matrix contract
├── C: blank project/rule generator
└── D: regional solver engine

Integration checkpoint I1
  cherry-pick A, B, C, D
  run complete software tests
  resolve only integration conflicts

Wave 2
├── E: complete schematic (depends on A+B+C)
├── F1: top-right region report (depends on B+D)
├── F2: Enter region report (depends on B+D)
├── F3: LShift region report (depends on B+D)
└── F4: RShift region report (depends on B+D)

Integration checkpoint I2
  cherry-pick E and all F reports
  run ERC and regional contract tests

Serial gate
  G: Update PCB from Schematic in KiCad UI

Wave 3 — SERIAL PCB OWNER ONLY
  H: apply all placements + outline
  I: route + zones
  J: manufacturing verification/export
```

Why Wave 3 is serial:

- all tasks would write `lh60.kicad_pcb`;
- PCB IPC targets one live document;
- separate worktrees cannot safely share one running PCB editor;
- cherry-picking independent board mutations is not conflict-safe.

## 7. Wave 1 Task Cards

### Agent A — RP2040-Tiny library

Prepared branch/worktree:

```text
branch: task/rp2040-tiny-lib
path: /data00/home/wangqiyilang/playground/lh60/.worktree/rp2040-tiny-lib/lh60
```

Write scope:

```text
lib/lh60-mcu/**
tools/lh60_design/mcu_library.py
tools/verify_lh60.py
```

Must not modify:

```text
docs/**
lh60.kicad_*
fp-lib-table
sym-lib-table
tools/lh60_design/layout.py
tools/lh60_design/matrix.py
tools/lh60_design/project.py
tools/lh60_design/regions.py
```

Seed WIP:

- use the uncommitted files listed in section 4.4;
- do not rewrite them from memory;
- finish the RED output test through Konnect-generated symbol/footprint.

Required deliverables:

```text
lib/lh60-mcu/lh60-mcu.kicad_sym
lib/lh60-mcu/lh60-mcu.pretty/MCU_RP2040-Tiny_SMD.kicad_mod
lib/lh60-mcu/RP2040-Tiny-V1.1.step
lib/lh60-mcu/LICENSE-LambdaKB-MIT.txt
lib/lh60-mcu/README.md
tools/lh60_design/mcu_library.py
tools/verify_lh60.py additions limited to Rp2040TinyContractTest
```

Acceptance:

```bash
python -m unittest -v tools.verify_lh60.Rp2040TinyContractTest
python -m compileall -q tools/lh60_design/mcu_library.py tools/verify_lh60.py
mkdir -p /tmp/lh60-mcu-svg
kicad-cli fp export svg --output /tmp/lh60-mcu-svg \
  lib/lh60-mcu/lh60-mcu.pretty
test "$(find /tmp/lh60-mcu-svg -name '*.svg' | wc -l)" -eq 1
git diff --check
```

Commit:

```text
feat(lib): add audited rp2040 tiny module
```

### Agent B — current layout and 10×7 matrix

Prepared branch/worktree:

```text
branch: task/layout-matrix
path: /data00/home/wangqiyilang/playground/lh60/.worktree/layout-matrix/lh60
```

Write scope:

```text
tools/lh60_design/layout.py
tools/lh60_design/matrix.py
tools/verify_layout_matrix.py
docs/layout-current.md
docs/current-baseline.md
docs/glossary.md
```

Important isolation choice:

- Do not edit `tools/verify_lh60.py`; Agent A owns that file.
- Put new tests in `tools/verify_layout_matrix.py`.

Required contracts:

- 75 physical sockets;
- 70 unique logical nodes;
- five shared-node groups;
- 10×7 row-major allocation;
- GPIO map in section 5.3;
- physical coordinates derived from current approved layout, not test board coordinates.

Acceptance:

```bash
python -m unittest -v tools.verify_layout_matrix
python -m compileall -q \
  tools/lh60_design/layout.py \
  tools/lh60_design/matrix.py \
  tools/verify_layout_matrix.py
git diff --check
```

Commit:

```text
docs: freeze current production layout
```

### Agent C — project/rule generator

Prepared branch/worktree:

```text
branch: task/project-skeleton
path: /data00/home/wangqiyilang/playground/lh60/.worktree/project-skeleton/lh60
```

Write scope:

```text
tools/lh60_design/project.py
tools/verify_project_contract.py
.konnect/project.json
```

Do not create production KiCad files in this task. They depend on Agent A's symbol/footprint library,
and parallel creation would collide with later integration. This agent produces an idempotent generator and
tests it only in `/tmp`.

Generator must expose:

```python
create_production_project(client, project_dir: Path) -> None
```

It must:

- create blank `lh60.kicad_pro/.sch/.pcb`;
- register portable `lh60-sockets` and `lh60-mcu` libraries;
- set board rules;
- set provisional 285.75 × 95.25 mm outline;
- refuse partial existing projects.

Acceptance:

```bash
rm -rf /tmp/lh60-project-contract
python -m unittest -v tools.verify_project_contract
python -m compileall -q \
  tools/lh60_design/project.py \
  tools/verify_project_contract.py
git diff --check
```

Commit:

```text
feat(project): add production project generator
```

### Agent D — regional solver engine

Prepared branch/worktree:

```text
branch: task/region-solver
path: /data00/home/wangqiyilang/playground/lh60/.worktree/region-solver/lh60
```

Write scope:

```text
tools/lh60_design/regions.py
tools/verify_region_solver.py
```

Do not create `docs/regions/*.json` yet; Wave 2 region agents own those outputs.

Solver interfaces:

```python
solve_region(region: RegionSpec) -> RegionReport
enumerate_rotations(...) -> tuple[...]
measure_clearances(...) -> ClearanceReport
```

Hard limits:

```text
copper >= 0.25 mm
hole edge hard minimum >= 0.45 mm
hole edge target >= 0.50 mm
courtyard overlap == 0 after each footprint's 0.50 mm buffer
```

Acceptance:

```bash
python -m unittest -v tools.verify_region_solver
python -m compileall -q \
  tools/lh60_design/regions.py \
  tools/verify_region_solver.py
git diff --check
```

Commit:

```text
feat(layout): add multi-layout solver
```

## 8. Wave 2 Task Cards

Wave 2 branches start from Integration Checkpoint I1, not `63a3072`.

### Agent E — complete schematic

Write scope:

```text
tools/lh60_design/schematic.py
tools/verify_schematic_contract.py
lh60.kicad_sch
```

Inputs:

- Agent A MCU library;
- Agent B matrix/layout;
- Agent C production project.

Must generate through Konnect:

```text
1 MCU
76 switch symbols
70 diodes
VSYS/3V3/GND test points
COL0..COL9 test points
ROW0..ROW6 test points
GP27/GP28/GP29 test points
```

Acceptance:

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

No unexplained ERC errors.

Commit:

```text
feat(sch): add production keyboard matrix
```

### Agents F1–F4 — independent regional reports

Each agent owns only one report and one test file:

| Agent | Write scope | Commit |
|---|---|---|
| F1 | `docs/regions/top-right.json`, `tools/verify_region_top_right.py` | `feat(layout): solve top-right layout` |
| F2 | `docs/regions/enter.json`, `tools/verify_region_enter.py` | `feat(layout): solve enter layout` |
| F3 | `docs/regions/lshift.json`, `tools/verify_region_lshift.py` | `feat(layout): solve left-shift layout` |
| F4 | `docs/regions/rshift.json`, `tools/verify_region_rshift.py` | `feat(layout): solve right-shift layout` |

Rules:

- use Agent D solver;
- create temporary coupon only in `/tmp`;
- no production `.kicad_pcb` write;
- try single G first, then Dual upgrades;
- report every placement, rotation, logical node, and minimum clearance;
- if unsolved, commit the failure report with actual/required/shortfall and stop that region only.

## 9. Wave 3 Serial PCB Ownership

After Wave 2 integration, assign one PCB owner. That agent owns:

```text
lh60.kicad_pcb
tools/lh60_design/pcb.py
tools/verify_pcb_contract.py
FabOutput/ local only
```

Sequence:

1. KiCad UI: Update PCB from Schematic.
2. Apply all fixed-key and region placements.
3. Place MCU, diodes, test pads.
4. Finalize outline.
5. Route.
6. Add/refill GND zones.
7. DRC/ERC/design review/DFM.
8. Export manufacturing package.

Do not split these writes across agents.

## 10. Coordinator Integration Commands

Create task branches from clean root repository:

```bash
cd /data00/home/wangqiyilang/playground/lh60
git fetch origin
test "$(git rev-parse origin/lh60-rp2040-v2)" = \
  "63a3072ba9f8ad063f86f7e543b49cf2b50fba74"
```

After Wave 1 agents return:

```bash
cd /data00/home/wangqiyilang/playground/lh60/.worktree/lh60-rp2040-v2/lh60
git status --short
git cherry-pick <agent-a-sha>
git cherry-pick <agent-b-sha>
git cherry-pick <agent-c-sha>
git cherry-pick <agent-d-sha>
python -m unittest discover -v tools
git diff --check
git push origin lh60-rp2040-v2
```

The expected integration conflict is test aggregation only:

- Agent A edits `tools/verify_lh60.py`.
- Agents B/C/D use separate verification files and should cherry-pick cleanly.

After Wave 2:

```bash
git cherry-pick <agent-e-sha>
git cherry-pick <agent-f1-sha>
git cherry-pick <agent-f2-sha>
git cherry-pick <agent-f3-sha>
git cherry-pick <agent-f4-sha>
python -m unittest discover -v tools
git diff --check
git push origin lh60-rp2040-v2
```

## 11. Copy-ready Subagent Prompts

### Prompt A

```text
You own the RP2040-Tiny library unit in the LH60 repository.

Repo/worktree: /data00/home/wangqiyilang/playground/lh60/.worktree/rp2040-tiny-lib/lh60
Base commit: 63a3072ba9f8ad063f86f7e543b49cf2b50fba74

Read:
- docs/superpowers/specs/2026-08-15-lh60-production-v2-design.md
- docs/superpowers/plans/2026-08-15-lh60-production-v2.md Task 4
- docs/handoff/2026-08-16-lh60-production-parallel-handoff.md Agent A
- /data00/home/wangqiyilang/.agents/skills/konnect/SKILL.md
- /data00/home/wangqiyilang/.agents/skills/kicad-library/SKILL.md

Exclusive write scope:
- lib/lh60-mcu/**
- tools/lh60_design/mcu_library.py
- tools/verify_lh60.py, but only Rp2040TinyContractTest additions

Current WIP to preserve:
- pure 23-pin contract test passes
- pure LambdaKB SMD coordinate contract passes
- output contract is RED because lh60-mcu.kicad_sym is not generated
- official STEP and LambdaKB MIT license have already been downloaded

Finish test-first. All .kicad_sym/.kicad_mod writes must use Konnect MCP.
Create provenance README, generate symbol/footprint, verify VSYS not 5V, associate official STEP,
run the exact acceptance commands in the handoff, commit, push task branch.

Commit title:
feat(lib): add audited rp2040 tiny module

Commit trailer:
Co-authored-by: TRAE CLI <noreply@bytedance.com>

Return:
- commit SHA
- changed files
- exact test output summary
- any residual blocker
```

### Prompt B

```text
You own the current physical layout and 10×7 matrix contract for LH60.

Repo/worktree: /data00/home/wangqiyilang/playground/lh60/.worktree/layout-matrix/lh60
Base commit: 63a3072ba9f8ad063f86f7e543b49cf2b50fba74

Read:
- approved design spec
- implementation plan Task 5
- parallel handoff Agent B and shared contracts

Exclusive write scope:
- tools/lh60_design/layout.py
- tools/lh60_design/matrix.py
- tools/verify_layout_matrix.py
- docs/layout-current.md
- docs/current-baseline.md
- docs/glossary.md

Do not edit tools/verify_lh60.py or any KiCad source file.

Implement 75 physical sockets, 70 logical nodes, five shared-node groups, 10×7 row-major
allocation, GP0..GP9 columns, GP10..GP15+GP26 rows, GP27..GP29 spares. Preserve
the retired `SW59` reference slot and keep active references through `SW76`.
Use current approved 15u×5 layout only; do not copy test-board coordinates or rotations.

Run handoff acceptance, commit and push.

Commit title:
docs: freeze current production layout

Return commit SHA, changed files, tests, and any ambiguity found.
```

### Prompt C

```text
You own the production project/rule generator, not the production KiCad files.

Repo/worktree: /data00/home/wangqiyilang/playground/lh60/.worktree/project-skeleton/lh60
Base commit: 63a3072ba9f8ad063f86f7e543b49cf2b50fba74

Read design spec, implementation plan Task 6, and handoff Agent C.

Exclusive write scope:
- tools/lh60_design/project.py
- tools/verify_project_contract.py
- .konnect/project.json

Do not create or commit lh60.kicad_pro/.sch/.pcb, fp-lib-table, or sym-lib-table.
Test the generator only in /tmp through Konnect MCP.

Implement idempotent create_production_project(client, project_dir) with portable library
registrations, exact board rules, and provisional outline. Refuse partial existing projects.

Run acceptance, commit and push.

Commit title:
feat(project): add production project generator

Return commit SHA, changed files, tests, and blockers.
```

### Prompt D

```text
You own the reusable multi-layout region solver only.

Repo/worktree: /data00/home/wangqiyilang/playground/lh60/.worktree/region-solver/lh60
Base commit: 63a3072ba9f8ad063f86f7e543b49cf2b50fba74

Read design spec section 10, implementation plan Task 9, and handoff Agent D.

Exclusive write scope:
- tools/lh60_design/regions.py
- tools/verify_region_solver.py

Do not write production KiCad files or docs/regions outputs.

Implement deterministic rotation enumeration and clearance measurement for G and Dual socket
specs. Hard gates: copper 0.25, hole edge hard 0.45, target 0.50, no courtyard overlap.
Failure reports must include actual, required, shortfall, and involved objects.

Run acceptance, commit and push.

Commit title:
feat(layout): add multi-layout solver

Return commit SHA, changed files, tests, and solver limitations.
```

### Prompt E

```text
You own the production schematic after Wave 1 has been integrated.

Base: coordinator-provided Integration Checkpoint I1 SHA.
Read design spec, plan Task 7, handoff Agent E, layout/matrix modules, and MCU/project generators.

Exclusive write scope:
- tools/lh60_design/schematic.py
- tools/verify_schematic_contract.py
- lh60.kicad_sch through Konnect MCP only

Do not modify lh60.kicad_pcb or library footprints.

Generate 1 MCU, 76 switch symbols, 70 SOD-323 diodes, matrix and power/spare test points,
and exact COL2ROW connectivity. Search registered libraries; do not guess symbol/footprint IDs.
Run all schematic checks and ERC in the handoff.

Commit title:
feat(sch): add production keyboard matrix

Return commit SHA, component counts, ERC summary, changed files, blockers.
```

### Prompt F template

```text
You own only the <REGION> multi-layout report after Wave 1 integration.

Base: coordinator-provided Integration Checkpoint I1 SHA.
Exclusive write scope:
- docs/regions/<FILE>.json
- tools/verify_region_<SUFFIX>.py

Use tools/lh60_design/regions.py and layout.py.
Create temporary KiCad coupon only in /tmp through Konnect.
Do not modify production lh60.kicad_pcb.

Solve all mutually exclusive sockets simultaneously:
1. single G rotations first
2. attempt Dual upgrades
3. enforce copper/hole/courtyard hard gates

If no solution, commit a failure report with actual/required/shortfall and minimum-change alternatives.

Commit title:
feat(layout): solve <REGION> layout

Return commit SHA, result status, placements/rotations, minimum clearances, DRC summary.
```

## 12. Known Risks

1. The current layout source was historically written with 18×17 values in archived notes; production
   conversion must use 19.05×19.05.
2. RShift test-board coordinates are not production coordinates. Only the functional options are retained.
3. Dual courtyard must be the merged external boundary; two overlapping closed contours caused KiCad
   `malformed_courtyard`.
4. KiCad 10 PCB sync is a GUI gate.
5. No display is available in the current shell environment; the user may need to open KiCad and run
   Update PCB from Schematic.
6. Production approval still requires a fabricated Dual coupon with both sockets soldered.

## 13. Handoff Completion Criteria

The handoff itself is complete when:

- current branch/commit and WIP ownership are accurate;
- every parallel task has disjoint write scope;
- every task has exact acceptance and commit contract;
- PCB writes are explicitly serialized;
- prompts are self-contained and copy-ready.
