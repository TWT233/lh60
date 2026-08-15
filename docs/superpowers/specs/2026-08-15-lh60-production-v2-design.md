# LH60 RP2040 V2 Production Design

## 1. Goal

从空白 KiCad 工程实现 LH60 RP2040 V2 生产板，不复制旧生产工程或
`test/` 中任何测试板的坐标、旋转、走线、板框或 DRC 结论。

本轮交付目标：

- 建立 Gateron LP、Kailh Choc V1/V2、Gateron LP + Choc V1 三套参数化
  socket footprint 产品线；
- 使用 Waveshare RP2040-Tiny 和随附 8-pin FPC USB-C 转接板；
- 实现最小有线键盘：主控、按键矩阵、每逻辑节点一颗二极管和调试焊盘；
- 在最终 KLE 到位后，从零求解四个多配列区域、矩阵、板框、布局和布线；
- 满足嘉立创当前常规双层板制造能力，并在最终板框冻结后进行实时计价。

## 2. Scope

### 2.1 Included

- KiCad 10 生产工程：
  - `lh60.kicad_pro`
  - `lh60.kicad_sch`
  - `lh60.kicad_pcb`
- 21 个参数化 socket footprint；
- RP2040-Tiny 项目级符号、SMD footprint 和官方 STEP 模型；
- `1N4148WS / SOD-323` 矩阵二极管；
- 电源、矩阵线和空闲 GPIO 测试焊盘；
- 四个多配列区域：
  - 顶排右端：`2u / 1u + 1u`
  - Enter：`2.25u / 1u + 1.25u`
  - LShift：`2.25u / 1u + 1.25u`
  - RShift：`2.75u / 1.75u + 1u / 1u + 1.75u`
- 嘉立创制造检查和生产文件导出。

### 2.2 Excluded

- RGB、旋钮、蜂鸣器、电池、无线和额外 USB 电路；
- 载板上的 RESET、BOOTSEL、RUN 或 SWD 接口；
- 安装孔；
- PCB stabilizer / 卫星轴孔或其他卫星轴结构；
- 外壳、定位板和 USB-C 子板设计；
- 装饰、产品名、版本号、Git 信息等额外丝印；
- 固定价格承诺。

## 3. Clean Production Project

- 删除整个 `test/`，包括测试 PCB、coupon、生成器、渲染图、旧 DRC 报告和测试脚本。
- 生产工程在仓库根目录通过 Konnect 从空白创建。
- 不从旧 `lh60.kicad_*`、归档工程或测试工程复制 KiCad 对象。
- 可复用验证逻辑放在 `tools/`；临时 coupon 和 KiCad 工程只在 `/tmp` 中通过
  Konnect 创建，不提交仓库。
- 所有 `.kicad_sch`、`.kicad_pcb`、`.kicad_pro`、`.kicad_sym`、
  `.kicad_mod` 和 library table 修改必须通过 Konnect MCP 完成。

## 4. Socket Library

### 4.1 Product Lines

`lib/lh60-sockets/` 是唯一自有 socket footprint 库。参数化工具生成以下 21 个
footprint：

| Series | Capability | Sizes |
|---|---|---|
| `Gateron-LP-Hotswap-Socket-{U}` | Gateron LP / KS-33 | `1U`, `1.25U`, `1.5U`, `1.75U`, `2U`, `2.25U`, `2.75U` |
| `Kailh-Choc-V1V2-Hotswap-Socket-{U}` | Kailh Choc V1 / V2 | 同上 |
| `Gateron-LP-or-ChocV1-Hotswap-Socket-{U}` | Gateron LP + Choc V1 | 同上 |

U 数只决定键帽包络，不决定是否使用 stabilizer。PCB 不提供 stabilizer 结构；
稳定方式由后续定位板决定。

### 4.2 Common Contract

- 所有 footprint 只暴露 logical pad `1` 和 `2`。
- 同一 footprint 内属于同一触点的多个铜形状使用相同 pad number。
- `Dwgs.User`：宽 `U × 19.05 mm`、高 `19.05 mm` 的键帽包络。
- `B.Fab`：真实 socket 座体、端子和装配方向。
- `B.CrtYd`：真实座体、端子和完整 land pattern 的几何并集，再整体外扩
  `0.50 mm` 装配余量。
- 不使用生产 `F.SilkS` 绘制键帽网格。
- Socket 保留 BOM 语义，设置 `exclude_from_pos_files`，不进入 PnP 坐标。
- G、K、Dual 分别关联对应的已审计 STEP；Dual 同时关联 Gateron 和 Choc V1。
- 同系列七个 U 数除 `Dwgs.User` 键帽包络外，pad、孔、`B.Fab`、
  `B.CrtYd`、属性和模型合同必须一致。
- Dual 的 KiCad 几何验证只证明设计文件中的座体模型可共存。量产批准前必须制造
  实物 coupon，同时焊接两种 socket，并分别验证 Gateron LP 与 Choc V1 开关的
  插入、锁定、拔出和电气导通。

### 4.3 Production Selection

- 固定且无重叠的键位默认使用 Dual，并同时焊接 Gateron LP 和 Choc V1 socket。
- 四个多配列区域先用单 G 从零求解所有 socket 同时存在的布局。
- 单 G 解成立后，再加入 Choc V1 孔、铜和 courtyard；仍满足规则时升级为 Dual。
- 单 K 是完整备选系列，本版生产板默认不使用。
- “支持切换”要求所有参与方案的 socket 同时焊在 PCB 背面；只预留空焊盘不算完成。

## 5. RP2040-Tiny

### 5.1 Source Decision

Waveshare 提供 V1.1 原理图、尺寸图和 STEP，但没有官方 KiCad 库。KiCad 官方库也
没有 RP2040-Tiny。

使用 `LambdaKB/kicad-lkbd` 作为上游基准：

- upstream commit: `9bb38d7e67c561dfa24428686992abeb17d0a9aa`
- license: MIT
- footprint baseline: `MCU_RP2040-Tiny_SMD`

LambdaKB 的 23-pad SMD footprint、2.54 mm pad pitch 和 18 × 23.5 mm 模块外形
与 Waveshare 官方资料一致。项目内固化经过审计的版本，不依赖用户全局库。

LambdaKB 的符号继承 RP2040-Zero，并把 pin 23 命名为 `5V`；Waveshare
RP2040-Tiny V1.1 官方原理图将 pin 23 定义为 `VSYS`。项目版本必须修正该名称。

### 5.2 Pin Contract

| Module pin | Signal |
|---:|---|
| 1–9 | `GP0–GP8` |
| 10–14 | `GP9–GP13` |
| 15–16 | `GP14–GP15` |
| 17–20 | `GP26–GP29` |
| 21 | `3V3` |
| 22 | `GND` |
| 23 | `VSYS` |

模块半孔没有引出 SWDIO、SWCLK 或 RUN。RUN、BOOTSEL、USB D+/D− 和 USB 供电
只通过模块 FPC 与随附转接板使用，载板不创建虚假测试接口。

### 5.3 Placement

- 默认横向放在空格区域背面，FPC 朝后侧板边。
- 若最终 socket courtyard 与模块冲突，只调整主控位置，不改变电气合同。
- Footprint 关联 Waveshare 官方 `RP2040-Tiny V1.1.step`。

## 6. Electrical Architecture

### 6.1 Minimal Wired Keyboard

载板只包含：

- RP2040-Tiny；
- 按键矩阵；
- 每逻辑节点一颗二极管；
- 必要测试焊盘。

USB-C、供电转换、RESET 和 BOOTSEL 使用附赠 RP2040-Tiny Adapter，不在载板重复。

### 6.2 Matrix Selection

最终矩阵维度等待用户提供 KLE 后确定。右侧新增宏列和 `10 × 8` 只是候选，不提前冻结。

对最终逻辑节点数 `N`，从所有满足以下条件的组合中选择：

```text
rows × columns >= N
rows + columns <= 20
```

优先级：

1. GPIO 占用更少；
2. PCB 走线更短、交叉更少；
3. QMK 节点映射清晰；
4. 至少保留一个空闲 GPIO，能保留两个更优。

物理键盘行列不要求与电气矩阵行列一致。若采用 `10 × 8` 等非物理映射，必须交付
完整的物理键位 → 逻辑节点 → GPIO 映射表。

### 6.3 Diodes and Direction

- 每个逻辑节点一颗 `1N4148WS / SOD-323`。
- 统一采用 QMK `COL2ROW`：
  - 列线 → 二极管阳极；
  - 二极管阴极 → socket pad 1；
  - socket pad 2 → 行线。
- 同一逻辑键的多个互斥物理 socket 共用一颗二极管。
- 独立 Fn 等物理键使用独立逻辑节点。

### 6.4 Test Pads

PCB 背面集中保留：

- `VSYS`
- `3V3`
- `GND`
- 每条矩阵行线
- 每条矩阵列线
- 每个未使用 GPIO

不保留 SWD、RUN、BOOTSEL、USB D+/D− 测试点。

## 7. Assembly

- JLC SMT：所有 `1N4148WS / SOD-323` 二极管。
- 手焊：RP2040-Tiny 和全部 socket。
- 所有电子器件、socket 和测试点放 PCB 背面。
- 正面只保留轴体和定位板空间。
- Dual footprint 的两种 socket 均同时焊接。

## 8. PCB and Manufacturing

### 8.1 Current JLC Baseline

主要官方来源：

- 嘉立创《技术指导：下单前技术员必看》：
  `https://m.jlc.com/portal/server_guide_112.html`
  （当前 canonical 为 `server_guide_4110`）
- 嘉立创制造工艺要求：
  `https://www.jlc.com/portal/1/serviceGuide`

当前相关要求：

- 常规插件孔最小孔径 `0.50 mm`；
- 常规插件孔公差 `+0.13/-0.08 mm`；
- 过孔孔边间距最低 `0.20 mm`；
- 插件孔孔边间距最低 `0.45 mm`；
- 插件孔焊环推荐 `0.25 mm`，极限 `0.18 mm`；
- CNC 板边和内槽到铜：页面顶部提醒为 `0.30 mm`，正文最低为 `0.20 mm`；
- V-CUT 到铜至少 `0.40 mm`；
- 常规丝印线宽至少 `0.15 mm`、字高至少 `1.00 mm`；
- 2025-06 起新订单支持 LDI 1:1 阻焊开窗。

存在不同表述时采用更保守值。

### 8.2 Project Rules

- 层数：2 层；
- 普通信号线宽：`0.25 mm`；
- 普通铜间距：`0.25 mm`；
- 电源线宽：至少 `0.50 mm`；
- 过孔：`0.30 mm drill / 0.70 mm diameter`；
- 铜到 CNC 板边或内槽：至少 `0.50 mm`；
- 独立插件孔、开关孔和 socket 孔的孔边间距：
  - 目标至少 `0.50 mm`；
  - 绝不低于 `0.45 mm`；
- 不使用 HDI、盲埋孔、阻抗控制、塞孔、金手指或其他加价工艺。

最终板厚、铜厚、油墨和表面处理在板框冻结后按嘉立创实时低价选项确认。

“50 元打样”不是静态工艺标准。最终价格受板尺寸、数量、活动和表面处理影响；
最终 KLE 和板框确定后必须重新实时计价。价格超出预期时，只提出尺寸或工艺优化，
不擅自删键或降低兼容性。

## 9. PCB Layout

- 所有键位坐标、socket 旋转、主控位置、二极管位置、板框和走线从零求解。
- 不参考 `test/` 或旧生产工程的布局结果。
- 二极管靠近对应逻辑节点集中或分区放置，兼顾短走线和 JLC 单面 SMT。
- 布线完成后在双面添加 GND 铜皮，按需要增加 GND 过孔。
- 不为了铺铜牺牲 socket 孔位、孔间距或 courtyard。
- 不放安装孔。
- 不放产品名、版本、Git 信息或装饰丝印。
- 仅保留：
  - 参考编号；
  - 二极管极性；
  - 测试点网络名；
  - socket 装配方向。

## 10. Multi-layout Solver

四个区域分别作为独立机械求解单元，不共享测试板坐标或旋转假设。

每个区域交付：

- 所有 socket 中心坐标；
- 每个 socket 的旋转；
- 物理 socket 到逻辑节点的映射；
- 实际最小铜间距；
- 实际最小孔边间距；
- 实际最小 courtyard 间距；
- 区域级 DRC 结果。

先求解所有单 G socket 同时焊接；再尝试把可行位置升级为 Dual。

若某区域无解：

1. 记录冲突对象；
2. 记录实际距离、要求距离和缺口；
3. 给出最小化变更的备选方案；
4. 暂停该区域并请求用户裁决；
5. 继续不依赖该区域的其他单元。

未经用户明确确认，不得：

- 删除配列；
- 改成出厂装配二选一；
- 只留空焊盘并宣称可切换；
- 用旧测试结论豁免生产规则。

## 11. Pending KLE Gate

KLE 是以下内容的真实阻塞项：

- 是否增加右侧宏列；
- 最终键位、U 数和中心坐标；
- 物理布局宽高；
- 逻辑节点数量；
- 共享节点关系；
- 最终矩阵维度；
- 板框；
- 四个多配列区域的生产求解。

KLE 到位前可以完成：

- 删除 `test/`；
- 三套 socket 库；
- RP2040-Tiny 库；
- 制造规则；
- 空白生产工程骨架。

不得在 KLE 到位前猜测矩阵或生产布局。

## 12. Units, Dependencies, and Interfaces

### 12.1 Units

| Unit | Deliverable | Independent verification |
|---|---|---|
| U1 | Approved design specification | Document self-review |
| U2 | Remove complete `test/` tree | Git tree and status |
| U3 | 21-footprint socket library | Contract checks, KiCad parse/export, temporary DRC coupon |
| U4 | RP2040-Tiny symbol/footprint/model | Official 23-pin and mechanical audit |
| U5 | Empty production project and JLC rules | Project parse and rule query |
| U6 | KLE-derived geometry and matrix contract | Capacity and mapping checks |
| U7 | MCU, matrix, diode and test-pad schematic | ERC and connectivity checks |
| U8A | Top-right multi-layout solution | Regional DRC and geometry report |
| U8B | Enter multi-layout solution | Regional DRC and geometry report |
| U8C | LShift multi-layout solution | Regional DRC and geometry report |
| U8D | RShift multi-layout solution | Regional DRC and geometry report |
| U9 | Remaining PCB placement and routing | DRC and unrouted count |
| U10 | Integrated production package | ERC, DRC, DFM, Gerber/BOM/position export, live quote |

### 12.2 Dependency Graph

```text
U1
├── U2
├── U3
├── U4
└── U5

KLE ──> U6 ──> U7
           ├── U8A
           ├── U8B
           ├── U8C
           ├── U8D
           └── U9

U2 + U3 + U4 + U5 + U7 + U8A..U8D + U9 ──> U10
```

Dependency edge classification:

- `U3`, `U4`, `U5` depend only on the approved specification and can proceed independently.
- `KLE → U6` is a true blocker because node count and physical coordinates do not exist before KLE.
- `U6 → U7/U8/U9` is a true blocker because schematic capacity and PCB placement consume the
  frozen mapping.
- `U8A..U8D` share only the matrix/socket contracts and can run independently with disjoint
  regional write scopes.
- An unresolved `U8x` blocks only its own region and final `U10`, not the other U8 units or U9.

### 12.3 Shared Interfaces

#### Socket footprint

```text
library nickname: lh60-sockets
logical pads: 1, 2
key pitch: 19.05 mm
layers: Dwgs.User, B.Fab, B.CrtYd
assembly: bottom-side, hand solder, excluded from position files
```

#### RP2040-Tiny

```text
library nickname: lh60-mcu
symbol: RP2040-Tiny
footprint: MCU_RP2040-Tiny_SMD
pins: 1..23 exactly as section 5.2
```

#### Matrix node

```text
physical_key_id
logical_node_id
row_net
column_net
diode_ref
socket_refs[]
```

#### Multi-layout region report

```text
region
placements[]: {socket_ref, footprint, center_x_mm, center_y_mm, rotation_deg, logical_node_id}
minimum_copper_clearance_mm
minimum_hole_edge_clearance_mm
minimum_courtyard_clearance_mm
drc_status
blocking_conflicts[]
```

## 13. Verification

### 13.1 Footprints

- 3 series × 7 sizes = 21 footprint files.
- All expose only logical pad `1/2`.
- Same-series U variants differ only in keycap envelope.
- `B.Fab`, `B.CrtYd`, attributes and STEP contracts are present.
- `B.CrtYd` encloses the physical socket and complete land pattern with `0.50 mm` clearance.
- KiCad 10 parses and exports every footprint.
- Temporary clean coupon in `/tmp` has zero DRC violations.
- A fabricated Dual coupon passes simultaneous-socket assembly and switch insertion/removal checks
  before production approval.

### 13.2 RP2040-Tiny

- Compare all 23 pins against Waveshare V1.1 official schematic.
- Compare SMD pad coordinates and body outline against official dimensions.
- Verify pin 23 is `VSYS`, never `5V`.
- Verify FPC orientation and official STEP.
- Record LambdaKB source commit and MIT license.

### 13.3 Schematic

- KLE logical node count fits the selected matrix.
- GPIO allocation matches the matrix contract.
- Every logical node has exactly one diode.
- Shared sockets do not create duplicate nodes.
- Diodes are `COL2ROW`.
- ERC has no unexplained errors.
- Automated connectivity checks match the matrix mapping.

### 13.4 PCB

- Each multi-layout region has an independent geometry report.
- No short, unconnected item, copper clearance, hole clearance, courtyard, or edge violation.
- Final DRC is rerun after GND zone refill.
- JLC DFM checks pass.
- Gerber, drill, BOM and diode position files export successfully.
- Final board dimensions are submitted to live JLC pricing before production approval.

## 14. Commit and Delivery Discipline

Each unit is independently verified, committed and pushed before the next dependent unit:

1. design specification;
2. remove `test/`;
3. socket library;
4. RP2040-Tiny library;
5. KLE/matrix contract;
6. schematic;
7. each multi-layout region;
8. PCB placement/routing;
9. final manufacturing verification.

Every commit message ends with:

```text
Co-authored-by: TRAE CLI <noreply@bytedance.com>
```
