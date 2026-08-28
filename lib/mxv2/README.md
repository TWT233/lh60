# mxv2 — ai03 MX_V2 热插拔封装（vendored）

来源：https://github.com/ai03-2725/MX_V2（分支 main，2026-08 抓取）
协议：MIT License，Copyright (c) 2017 ai03。

本目录仅收录本设计需要的热插拔座子库，未做任何几何修改：

| 库 | 内容 | 用途 |
|---|---|---|
| `Gateron_KS33_Hotswap.pretty` | Gateron LP V1.0/V2.0（KS-27/KS-33）热插拔座，1U–7U + 3D STEP | 主选轴家族 |
| `Kailh_PG1353_Hotswap.pretty` | Kailh Choc V2（PG1353）热插拔座（CPG135001S30），1U–7U + 3D STEP | 待验证的 Choc 兼容线 |

## 使用注意（来自上游 README，2024-08-15 破坏性变更）

MX_V2 的热插拔封装默认"座子面朝上"（pads 在 F.Cu）。新工程放置后请**把封装翻面
（KiCad 按 `F`），使座子/焊盘在板底（B.Cu）**，与真实安装方向一致。

## 上游已知 TODO

- Gateron KS33 封装尚缺稳定器避让 keepout（2U 及以上大键用稳定器时注意）。
- 3D 模型引用的是相对路径 `./Gateron-KS33-Socket.step`，已随库同目录存放。
