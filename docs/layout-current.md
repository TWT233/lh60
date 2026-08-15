# LH60 当前生产配列与矩阵

> 本文是当前 15u 生产配列、物理 socket 与逻辑矩阵的唯一映射入口。历史 KLE
> 讨论和旧测试板坐标不具有生产约束力。

## 1. 冻结合同

- 键区：15u × 5 行，键距 19.05 × 19.05 mm，左上角为物理原点。
- 键中心：`(x + width / 2, row + 0.5)` u；毫米坐标为 u 坐标乘 19.05。
- 物理 socket：76 个；逻辑节点：70 个；每个逻辑节点一颗二极管。
- 矩阵：10 × 7，节点按首次出现的物理顺序分配：
  `matrix_row, matrix_column = divmod(logical_index, 10)`。
- 方向：QMK `COL2ROW`。
- 列：`COL0..COL9 = GP0..GP9`。
- 行：`ROW0..ROW6 = GP10..GP15, GP26`。
- 空闲 GPIO：`GP27`, `GP28`, `GP29`。
- 顶排右端、Enter、LShift、RShift 的 socket 中心由本文冻结，但封装旋转待区域求解；
  每个候选均搜索 `0° / 90° / 180° / 270°`。

## 2. 物理 Socket

`variant` 仅描述互斥配列语义；固定键使用 `fixed`。同一节点的多个物理 socket
必须连接到同一颗二极管。

| Physical ID | Label | Row | x / width (u) | Center (u) | Center (mm) | Logical node | Region / variant |
|---|---|---:|---:|---:|---:|---|---|
| `r0_esc_1u` | Esc | 0 | 0 / 1 | 0.5, 0.5 | 9.525, 9.525 | `r0_esc_1u` | fixed / fixed |
| `r0_1_1u` | 1 | 0 | 1 / 1 | 1.5, 0.5 | 28.575, 9.525 | `r0_1_1u` | fixed / fixed |
| `r0_2_1u` | 2 | 0 | 2 / 1 | 2.5, 0.5 | 47.625, 9.525 | `r0_2_1u` | fixed / fixed |
| `r0_3_1u` | 3 | 0 | 3 / 1 | 3.5, 0.5 | 66.675, 9.525 | `r0_3_1u` | fixed / fixed |
| `r0_4_1u` | 4 | 0 | 4 / 1 | 4.5, 0.5 | 85.725, 9.525 | `r0_4_1u` | fixed / fixed |
| `r0_5_1u` | 5 | 0 | 5 / 1 | 5.5, 0.5 | 104.775, 9.525 | `r0_5_1u` | fixed / fixed |
| `r0_6_1u` | 6 | 0 | 6 / 1 | 6.5, 0.5 | 123.825, 9.525 | `r0_6_1u` | fixed / fixed |
| `r0_7_1u` | 7 | 0 | 7 / 1 | 7.5, 0.5 | 142.875, 9.525 | `r0_7_1u` | fixed / fixed |
| `r0_8_1u` | 8 | 0 | 8 / 1 | 8.5, 0.5 | 161.925, 9.525 | `r0_8_1u` | fixed / fixed |
| `r0_9_1u` | 9 | 0 | 9 / 1 | 9.5, 0.5 | 180.975, 9.525 | `r0_9_1u` | fixed / fixed |
| `r0_0_1u` | 0 | 0 | 10 / 1 | 10.5, 0.5 | 200.025, 9.525 | `r0_0_1u` | fixed / fixed |
| `r0_minus_1u` | - | 0 | 11 / 1 | 11.5, 0.5 | 219.075, 9.525 | `r0_minus_1u` | fixed / fixed |
| `r0_equal_1u` | = | 0 | 12 / 1 | 12.5, 0.5 | 238.125, 9.525 | `r0_equal_1u` | fixed / fixed |
| `r0_top_2u` | Top 2u | 0 | 13 / 2 | 14, 0.5 | 266.700, 9.525 | `r0_top_2u` | top-right / wide |
| `r0_top_split_left_fn_1u` | Top split Fn | 0 | 13 / 1 | 13.5, 0.5 | 257.175, 9.525 | `r0_top_split_left_fn_1u` | top-right / split-left |
| `r0_top_split_right_1u` | Top split right | 0 | 14 / 1 | 14.5, 0.5 | 276.225, 9.525 | `r0_top_2u` | top-right / split-right |
| `r1_tab_1.5u` | Tab | 1 | 0 / 1.5 | 0.75, 1.5 | 14.288, 28.575 | `r1_tab_1.5u` | fixed / fixed |
| `r1_q_1u` | Q | 1 | 1.5 / 1 | 2, 1.5 | 38.100, 28.575 | `r1_q_1u` | fixed / fixed |
| `r1_w_1u` | W | 1 | 2.5 / 1 | 3, 1.5 | 57.150, 28.575 | `r1_w_1u` | fixed / fixed |
| `r1_e_1u` | E | 1 | 3.5 / 1 | 4, 1.5 | 76.200, 28.575 | `r1_e_1u` | fixed / fixed |
| `r1_r_1u` | R | 1 | 4.5 / 1 | 5, 1.5 | 95.250, 28.575 | `r1_r_1u` | fixed / fixed |
| `r1_t_1u` | T | 1 | 5.5 / 1 | 6, 1.5 | 114.300, 28.575 | `r1_t_1u` | fixed / fixed |
| `r1_y_1u` | Y | 1 | 6.5 / 1 | 7, 1.5 | 133.350, 28.575 | `r1_y_1u` | fixed / fixed |
| `r1_u_1u` | U | 1 | 7.5 / 1 | 8, 1.5 | 152.400, 28.575 | `r1_u_1u` | fixed / fixed |
| `r1_i_1u` | I | 1 | 8.5 / 1 | 9, 1.5 | 171.450, 28.575 | `r1_i_1u` | fixed / fixed |
| `r1_o_1u` | O | 1 | 9.5 / 1 | 10, 1.5 | 190.500, 28.575 | `r1_o_1u` | fixed / fixed |
| `r1_p_1u` | P | 1 | 10.5 / 1 | 11, 1.5 | 209.550, 28.575 | `r1_p_1u` | fixed / fixed |
| `r1_left_bracket_1u` | [ | 1 | 11.5 / 1 | 12, 1.5 | 228.600, 28.575 | `r1_left_bracket_1u` | fixed / fixed |
| `r1_right_bracket_1u` | ] | 1 | 12.5 / 1 | 13, 1.5 | 247.650, 28.575 | `r1_right_bracket_1u` | fixed / fixed |
| `r1_backslash_1.5u` | \ | 1 | 13.5 / 1.5 | 14.25, 1.5 | 271.463, 28.575 | `r1_backslash_1.5u` | fixed / fixed |
| `r2_caps_1.75u` | Caps | 2 | 0 / 1.75 | 0.875, 2.5 | 16.669, 47.625 | `r2_caps_1.75u` | fixed / fixed |
| `r2_a_1u` | A | 2 | 1.75 / 1 | 2.25, 2.5 | 42.863, 47.625 | `r2_a_1u` | fixed / fixed |
| `r2_s_1u` | S | 2 | 2.75 / 1 | 3.25, 2.5 | 61.913, 47.625 | `r2_s_1u` | fixed / fixed |
| `r2_d_1u` | D | 2 | 3.75 / 1 | 4.25, 2.5 | 80.963, 47.625 | `r2_d_1u` | fixed / fixed |
| `r2_f_1u` | F | 2 | 4.75 / 1 | 5.25, 2.5 | 100.013, 47.625 | `r2_f_1u` | fixed / fixed |
| `r2_g_1u` | G | 2 | 5.75 / 1 | 6.25, 2.5 | 119.062, 47.625 | `r2_g_1u` | fixed / fixed |
| `r2_h_1u` | H | 2 | 6.75 / 1 | 7.25, 2.5 | 138.113, 47.625 | `r2_h_1u` | fixed / fixed |
| `r2_j_1u` | J | 2 | 7.75 / 1 | 8.25, 2.5 | 157.162, 47.625 | `r2_j_1u` | fixed / fixed |
| `r2_k_1u` | K | 2 | 8.75 / 1 | 9.25, 2.5 | 176.213, 47.625 | `r2_k_1u` | fixed / fixed |
| `r2_l_1u` | L | 2 | 9.75 / 1 | 10.25, 2.5 | 195.263, 47.625 | `r2_l_1u` | fixed / fixed |
| `r2_semicolon_1u` | ; | 2 | 10.75 / 1 | 11.25, 2.5 | 214.312, 47.625 | `r2_semicolon_1u` | fixed / fixed |
| `r2_quote_1u` | ' | 2 | 11.75 / 1 | 12.25, 2.5 | 233.363, 47.625 | `r2_quote_1u` | fixed / fixed |
| `r2_enter_ansi_2.25u` | ANSI Enter | 2 | 12.75 / 2.25 | 13.875, 2.5 | 264.319, 47.625 | `r2_enter_ansi_2.25u` | enter / wide |
| `r2_enter_split_left_fn_1u` | Enter split Fn | 2 | 12.75 / 1 | 13.25, 2.5 | 252.413, 47.625 | `r2_enter_split_left_fn_1u` | enter / split-left |
| `r2_enter_split_right_1.25u` | Split Enter | 2 | 13.75 / 1.25 | 14.375, 2.5 | 273.844, 47.625 | `r2_enter_ansi_2.25u` | enter / split-right |
| `r3_lshift_split_left_fn_1u` | LShift split Fn | 3 | 0 / 1 | 0.5, 3.5 | 9.525, 66.675 | `r3_lshift_split_left_fn_1u` | lshift / split-left |
| `r3_lshift_2.25u` | LShift | 3 | 0 / 2.25 | 1.125, 3.5 | 21.431, 66.675 | `r3_lshift_2.25u` | lshift / wide |
| `r3_lshift_split_1.25u` | Split LShift | 3 | 1 / 1.25 | 1.625, 3.5 | 30.956, 66.675 | `r3_lshift_2.25u` | lshift / split-right |
| `r3_z_1u` | Z | 3 | 2.25 / 1 | 2.75, 3.5 | 52.388, 66.675 | `r3_z_1u` | fixed / fixed |
| `r3_x_1u` | X | 3 | 3.25 / 1 | 3.75, 3.5 | 71.438, 66.675 | `r3_x_1u` | fixed / fixed |
| `r3_c_1u` | C | 3 | 4.25 / 1 | 4.75, 3.5 | 90.487, 66.675 | `r3_c_1u` | fixed / fixed |
| `r3_v_1u` | V | 3 | 5.25 / 1 | 5.75, 3.5 | 109.538, 66.675 | `r3_v_1u` | fixed / fixed |
| `r3_b_1u` | B | 3 | 6.25 / 1 | 6.75, 3.5 | 128.588, 66.675 | `r3_b_1u` | fixed / fixed |
| `r3_n_1u` | N | 3 | 7.25 / 1 | 7.75, 3.5 | 147.638, 66.675 | `r3_n_1u` | fixed / fixed |
| `r3_m_1u` | M | 3 | 8.25 / 1 | 8.75, 3.5 | 166.688, 66.675 | `r3_m_1u` | fixed / fixed |
| `r3_comma_1u` | , | 3 | 9.25 / 1 | 9.75, 3.5 | 185.738, 66.675 | `r3_comma_1u` | fixed / fixed |
| `r3_period_1u` | . | 3 | 10.25 / 1 | 10.75, 3.5 | 204.787, 66.675 | `r3_period_1u` | fixed / fixed |
| `r3_slash_1u` | / | 3 | 11.25 / 1 | 11.75, 3.5 | 223.838, 66.675 | `r3_slash_1u` | fixed / fixed |
| `r3_rshift_2.75u` | RShift | 3 | 12.25 / 2.75 | 13.625, 3.5 | 259.556, 66.675 | `r3_rshift_2.75u` | rshift / wide |
| `r3_rshift_left_1.75u` | Left split RShift | 3 | 12.25 / 1.75 | 13.125, 3.5 | 250.031, 66.675 | `r3_rshift_2.75u` | rshift / split-left-shift |
| `r3_rshift_right_fn_1u` | Right split Fn | 3 | 14 / 1 | 14.5, 3.5 | 276.225, 66.675 | `r3_rshift_left_fn_1u` | rshift / split-right-fn |
| `r3_rshift_left_fn_1u` | Left split Fn | 3 | 12.25 / 1 | 12.75, 3.5 | 242.888, 66.675 | `r3_rshift_left_fn_1u` | rshift / split-left-fn |
| `r3_rshift_right_1.75u` | Right split RShift | 3 | 13.25 / 1.75 | 14.125, 3.5 | 269.081, 66.675 | `r3_rshift_2.75u` | rshift / split-right-shift |
| `r4_left_ctrl_1.25u` | Left Ctrl | 4 | 0 / 1.25 | 0.625, 4.5 | 11.906, 85.725 | `r4_left_ctrl_1.25u` | fixed / fixed |
| `r4_left_win_1.25u` | Left Win | 4 | 1.25 / 1.25 | 1.875, 4.5 | 35.719, 85.725 | `r4_left_win_1.25u` | fixed / fixed |
| `r4_left_alt_1.25u` | Left Alt | 4 | 2.5 / 1.25 | 3.125, 4.5 | 59.531, 85.725 | `r4_left_alt_1.25u` | fixed / fixed |
| `r4_space_2.25u` | Space | 4 | 3.75 / 2.25 | 4.875, 4.5 | 92.869, 85.725 | `r4_space_2.25u` | fixed / fixed |
| `r4_fn_1u` | Fn | 4 | 6 / 1 | 6.5, 4.5 | 123.825, 85.725 | `r4_fn_1u` | fixed / fixed |
| `r4_left_1u` | Left | 4 | 7 / 1 | 7.5, 4.5 | 142.875, 85.725 | `r4_left_1u` | fixed / fixed |
| `r4_down_1u` | Down | 4 | 8 / 1 | 8.5, 4.5 | 161.925, 85.725 | `r4_down_1u` | fixed / fixed |
| `r4_up_1u` | Up | 4 | 9 / 1 | 9.5, 4.5 | 180.975, 85.725 | `r4_up_1u` | fixed / fixed |
| `r4_right_1u` | Right | 4 | 10 / 1 | 10.5, 4.5 | 200.025, 85.725 | `r4_right_1u` | fixed / fixed |
| `r4_right_fn_1u` | Right Fn | 4 | 11 / 1 | 11.5, 4.5 | 219.075, 85.725 | `r4_right_fn_1u` | fixed / fixed |
| `r4_right_alt_1u` | Right Alt | 4 | 12 / 1 | 12.5, 4.5 | 238.125, 85.725 | `r4_right_alt_1u` | fixed / fixed |
| `r4_right_win_1u` | Right Win | 4 | 13 / 1 | 13.5, 4.5 | 257.175, 85.725 | `r4_right_win_1u` | fixed / fixed |
| `r4_right_ctrl_1u` | Right Ctrl | 4 | 14 / 1 | 14.5, 4.5 | 276.225, 85.725 | `r4_right_ctrl_1u` | fixed / fixed |

## 3. 逻辑节点与 10 × 7 矩阵

GPIO 列按 `GP0..GP9`，GPIO 行按 `GP10..GP15, GP26`。表中多个 physical ID
表示一组互斥 socket 共享同一节点和二极管。

| Index | Logical node | Matrix | Diode | Physical sockets |
|---:|---|---|---|---|
| 0 | `r0_esc_1u` | ROW0 / COL0 | D1 | `r0_esc_1u` |
| 1 | `r0_1_1u` | ROW0 / COL1 | D2 | `r0_1_1u` |
| 2 | `r0_2_1u` | ROW0 / COL2 | D3 | `r0_2_1u` |
| 3 | `r0_3_1u` | ROW0 / COL3 | D4 | `r0_3_1u` |
| 4 | `r0_4_1u` | ROW0 / COL4 | D5 | `r0_4_1u` |
| 5 | `r0_5_1u` | ROW0 / COL5 | D6 | `r0_5_1u` |
| 6 | `r0_6_1u` | ROW0 / COL6 | D7 | `r0_6_1u` |
| 7 | `r0_7_1u` | ROW0 / COL7 | D8 | `r0_7_1u` |
| 8 | `r0_8_1u` | ROW0 / COL8 | D9 | `r0_8_1u` |
| 9 | `r0_9_1u` | ROW0 / COL9 | D10 | `r0_9_1u` |
| 10 | `r0_0_1u` | ROW1 / COL0 | D11 | `r0_0_1u` |
| 11 | `r0_minus_1u` | ROW1 / COL1 | D12 | `r0_minus_1u` |
| 12 | `r0_equal_1u` | ROW1 / COL2 | D13 | `r0_equal_1u` |
| 13 | `r0_top_2u` | ROW1 / COL3 | D14 | `r0_top_2u`, `r0_top_split_right_1u` |
| 14 | `r0_top_split_left_fn_1u` | ROW1 / COL4 | D15 | `r0_top_split_left_fn_1u` |
| 15 | `r1_tab_1.5u` | ROW1 / COL5 | D16 | `r1_tab_1.5u` |
| 16 | `r1_q_1u` | ROW1 / COL6 | D17 | `r1_q_1u` |
| 17 | `r1_w_1u` | ROW1 / COL7 | D18 | `r1_w_1u` |
| 18 | `r1_e_1u` | ROW1 / COL8 | D19 | `r1_e_1u` |
| 19 | `r1_r_1u` | ROW1 / COL9 | D20 | `r1_r_1u` |
| 20 | `r1_t_1u` | ROW2 / COL0 | D21 | `r1_t_1u` |
| 21 | `r1_y_1u` | ROW2 / COL1 | D22 | `r1_y_1u` |
| 22 | `r1_u_1u` | ROW2 / COL2 | D23 | `r1_u_1u` |
| 23 | `r1_i_1u` | ROW2 / COL3 | D24 | `r1_i_1u` |
| 24 | `r1_o_1u` | ROW2 / COL4 | D25 | `r1_o_1u` |
| 25 | `r1_p_1u` | ROW2 / COL5 | D26 | `r1_p_1u` |
| 26 | `r1_left_bracket_1u` | ROW2 / COL6 | D27 | `r1_left_bracket_1u` |
| 27 | `r1_right_bracket_1u` | ROW2 / COL7 | D28 | `r1_right_bracket_1u` |
| 28 | `r1_backslash_1.5u` | ROW2 / COL8 | D29 | `r1_backslash_1.5u` |
| 29 | `r2_caps_1.75u` | ROW2 / COL9 | D30 | `r2_caps_1.75u` |
| 30 | `r2_a_1u` | ROW3 / COL0 | D31 | `r2_a_1u` |
| 31 | `r2_s_1u` | ROW3 / COL1 | D32 | `r2_s_1u` |
| 32 | `r2_d_1u` | ROW3 / COL2 | D33 | `r2_d_1u` |
| 33 | `r2_f_1u` | ROW3 / COL3 | D34 | `r2_f_1u` |
| 34 | `r2_g_1u` | ROW3 / COL4 | D35 | `r2_g_1u` |
| 35 | `r2_h_1u` | ROW3 / COL5 | D36 | `r2_h_1u` |
| 36 | `r2_j_1u` | ROW3 / COL6 | D37 | `r2_j_1u` |
| 37 | `r2_k_1u` | ROW3 / COL7 | D38 | `r2_k_1u` |
| 38 | `r2_l_1u` | ROW3 / COL8 | D39 | `r2_l_1u` |
| 39 | `r2_semicolon_1u` | ROW3 / COL9 | D40 | `r2_semicolon_1u` |
| 40 | `r2_quote_1u` | ROW4 / COL0 | D41 | `r2_quote_1u` |
| 41 | `r2_enter_ansi_2.25u` | ROW4 / COL1 | D42 | `r2_enter_ansi_2.25u`, `r2_enter_split_right_1.25u` |
| 42 | `r2_enter_split_left_fn_1u` | ROW4 / COL2 | D43 | `r2_enter_split_left_fn_1u` |
| 43 | `r3_lshift_split_left_fn_1u` | ROW4 / COL3 | D44 | `r3_lshift_split_left_fn_1u` |
| 44 | `r3_lshift_2.25u` | ROW4 / COL4 | D45 | `r3_lshift_2.25u`, `r3_lshift_split_1.25u` |
| 45 | `r3_z_1u` | ROW4 / COL5 | D46 | `r3_z_1u` |
| 46 | `r3_x_1u` | ROW4 / COL6 | D47 | `r3_x_1u` |
| 47 | `r3_c_1u` | ROW4 / COL7 | D48 | `r3_c_1u` |
| 48 | `r3_v_1u` | ROW4 / COL8 | D49 | `r3_v_1u` |
| 49 | `r3_b_1u` | ROW4 / COL9 | D50 | `r3_b_1u` |
| 50 | `r3_n_1u` | ROW5 / COL0 | D51 | `r3_n_1u` |
| 51 | `r3_m_1u` | ROW5 / COL1 | D52 | `r3_m_1u` |
| 52 | `r3_comma_1u` | ROW5 / COL2 | D53 | `r3_comma_1u` |
| 53 | `r3_period_1u` | ROW5 / COL3 | D54 | `r3_period_1u` |
| 54 | `r3_slash_1u` | ROW5 / COL4 | D55 | `r3_slash_1u` |
| 55 | `r3_rshift_2.75u` | ROW5 / COL5 | D56 | `r3_rshift_2.75u`, `r3_rshift_left_1.75u`, `r3_rshift_right_1.75u` |
| 56 | `r3_rshift_left_fn_1u` | ROW5 / COL6 | D57 | `r3_rshift_left_fn_1u`, `r3_rshift_right_fn_1u` |
| 57 | `r4_left_ctrl_1.25u` | ROW5 / COL7 | D58 | `r4_left_ctrl_1.25u` |
| 58 | `r4_left_win_1.25u` | ROW5 / COL8 | D59 | `r4_left_win_1.25u` |
| 59 | `r4_left_alt_1.25u` | ROW5 / COL9 | D60 | `r4_left_alt_1.25u` |
| 60 | `r4_space_2.25u` | ROW6 / COL0 | D61 | `r4_space_2.25u` |
| 61 | `r4_fn_1u` | ROW6 / COL1 | D62 | `r4_fn_1u` |
| 62 | `r4_left_1u` | ROW6 / COL2 | D63 | `r4_left_1u` |
| 63 | `r4_down_1u` | ROW6 / COL3 | D64 | `r4_down_1u` |
| 64 | `r4_up_1u` | ROW6 / COL4 | D65 | `r4_up_1u` |
| 65 | `r4_right_1u` | ROW6 / COL5 | D66 | `r4_right_1u` |
| 66 | `r4_right_fn_1u` | ROW6 / COL6 | D67 | `r4_right_fn_1u` |
| 67 | `r4_right_alt_1u` | ROW6 / COL7 | D68 | `r4_right_alt_1u` |
| 68 | `r4_right_win_1u` | ROW6 / COL8 | D69 | `r4_right_win_1u` |
| 69 | `r4_right_ctrl_1u` | ROW6 / COL9 | D70 | `r4_right_ctrl_1u` |

## 4. 五组共享节点

1. 顶排 `2u` 与 split-right `1u`。
2. ANSI Enter `2.25u` 与 split-right Enter `1.25u`。
3. LShift `2.25u` 与 split Shift `1.25u`。
4. RShift `2.75u`、left `1.75u`、right `1.75u`。
5. RShift left Fn `1u` 与 right Fn `1u`。

顶排、Enter 和 LShift 的 split-left Fn 各自是独立逻辑节点。四个区域的旋转和
最小铜、孔边、courtyard 间距由后续区域求解报告决定，不在本文预判。
