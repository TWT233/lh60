# LH60 Socket B.CrtYd Design

## Goal

为 `lib/lh60-sockets/` 中的自有 footprint 增加真实的底面座子占地，使 KiCad 能通过
`B.CrtYd` 检测座子实体的装配干涉，而不是使用开关本体或键帽外框作为 courtyard。

## Scope

- 更新 7 个 Gateron LP 单座 footprint：
  - `Gateron-LP-Hotswap-Socket-1U`
  - `Gateron-LP-Hotswap-Socket-1.25U`
  - `Gateron-LP-Hotswap-Socket-1.5U`
  - `Gateron-LP-Hotswap-Socket-1.75U`
  - `Gateron-LP-Hotswap-Socket-2U`
  - `Gateron-LP-Hotswap-Socket-2.25U`
  - `Gateron-LP-Hotswap-Socket-2.75U`
- 更新 1 个 Gateron LP + Choc V1 双座 footprint：
  - `Gateron-LP-or-ChocV1-Hotswap-Socket-1U`
- 不修改 pad、孔位、F.SilkS 键帽框、网络编号或其他 KiCad 工程文件。

## Courtyard Rule

- courtyard 只表示 PCB 底面的热插拔座实体，不表示顶面的开关外壳、键帽或定位板。
- 以座子最大实体外形为基准，四周增加 0.25mm 装配余量。
- 使用 `B.CrtYd`、0.05mm 线宽、无填充的轴对齐矩形。
- 双座 footprint 保留两块独立 courtyard，不画一个包围两者的大矩形。
- 不增加 `F.CrtYd`。

## Gateron LP Geometry

参考 `docs/O1CN01bK2mBI1wGI35HnOHL_!!51786280.jpg`：

- 座子最大外形：15.1mm × 5.4mm。
- siderakb 源封装 `B.Fab` 的塑胶主体中心为 `(-0.895, 5.225)`，与图纸
  11.85mm × 5.40mm 主体一致。
- 在最大外形四周增加 0.25mm 后，所有 Gateron 单座 footprint 使用：
  - 左上：`(-8.695, 2.275)`
  - 右下：`(6.905, 8.175)`

## Choc V1 Geometry

参考 Kailh `CPG135001S30` 官方/LCSC 图纸：

- 座子最大外形：13.15mm × 6.85mm。
- siderakb 源封装底面轮廓中心为 `(-2.5, 4.85)`。
- Choc V1 在双座 footprint 中旋转 180°。
- 旋转后再在四周增加 0.25mm，双座 footprint 中的 Choc V1 courtyard 使用：
  - 左上：`(-4.325, -8.525)`
  - 右下：`(9.325, -1.175)`

## Expected Behavior

- Gateron 单座 footprint 只显示一块底面 courtyard。
- 双座 footprint 显示上下分离的两块底面 courtyard：
  - 下方为 Gateron LP 0°。
  - 上方为 Choc V1 180°。
- 两块 courtyard 最近的 Y 向间隙约为 3.45mm，表示两种座子可同时贴装。
- 多配列 footprint 靠得过近时，KiCad courtyard DRC 应报告真实的底面座子装配冲突。

## Verification

1. 使用 Konnect library 工具读取每个 footprint，确认 `B.CrtYd` 数量：
   - Gateron 单座：1 个矩形。
   - 双座：2 个矩形。
2. 确认所有矩形线宽为 0.05mm，坐标与本规格一致。
3. 确认 pad 数量、pad 坐标和钻孔尺寸未变化。
4. 用 KiCad CLI 或 Konnect 导出 footprint/测试板视图，确认 courtyard 在底层且轮廓可见。
5. 更新 `lib/lh60-sockets/README.md`，删除“无 courtyard”旧口径并记录实际坐标规则。
