# lh60-sockets — LH60 项目自用座子库

`Gateron-LP-Hotswap-Socket-1U.kicad_mod`：Gateron LP（KS-27/KS-33）热插拔座
"纯座子"几何——**B.Cu SMD 焊盘 + 3 个非镀通孔**，无 THT 引脚、无电气孔。

来源：从 beekeeb Corne GLP（在售产品，MIT）量产 PCB 内嵌封装提取，仅做
去板级内容处理（删 net/path/坐标），几何未改。beekeeb 版与 siderakb
`HotSwap_THT` 同几何，但删去了 siderakb 为"无底座直焊"兼容而加的
THT 引脚/电气孔——LH60 不需要兼容无底座，故采用此版。

座子几何（相对中心）：

| 项目 | 位置 | 尺寸 |
|---|---|---:|
| 开关孔 NPTH | (0,0) | φ5.25 |
| 定位孔 NPTH | (−4.4,4.7) / (2.6,5.75) | φ3 |
| SMD 焊盘（B.Cu） | (−8.075,4.7) / (6.275,5.75) | 2.5×2.55 |

使用：每个键位中心放一个 1U 座子即可（键帽包络只是图形，座子本身恒为 1U）；
放置后默认焊盘已在 B.Cu（座子焊板底，与 Gateron 官方一致）。

协议：beekeeb Corne GLP（MIT）；几何源自 siderakb/key-switches.pretty
（CERN-OHL-P v2）。
