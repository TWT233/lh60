from __future__ import annotations

from dataclasses import dataclass


KEY_PITCH_MM = 19.05
REGION_ROTATIONS_DEG = {
    "top-right": (0, 90, 180, 270),
    "enter": (0, 90, 180, 270),
    "lshift": (0, 90, 180, 270),
    "rshift": (0, 90, 180, 270),
}


@dataclass(frozen=True)
class PhysicalKey:
    physical_key_id: str
    label: str
    row: int
    x_u: float
    width_u: float
    logical_node_id: str
    region: str | None = None
    variant: str = "fixed"

    @property
    def center_x_u(self) -> float:
        return self.x_u + self.width_u / 2

    @property
    def center_y_u(self) -> float:
        return self.row + 0.5

    @property
    def center_x_mm(self) -> float:
        return self.center_x_u * KEY_PITCH_MM

    @property
    def center_y_mm(self) -> float:
        return self.center_y_u * KEY_PITCH_MM

    @property
    def footprint_size(self) -> str:
        return f"{self.width_u:g}U"


def _key(
    physical_key_id: str,
    label: str,
    row: int,
    x_u: float,
    width_u: float = 1.0,
    *,
    logical_node_id: str | None = None,
    region: str | None = None,
    variant: str = "fixed",
) -> PhysicalKey:
    return PhysicalKey(
        physical_key_id=physical_key_id,
        label=label,
        row=row,
        x_u=x_u,
        width_u=width_u,
        logical_node_id=logical_node_id or physical_key_id,
        region=region,
        variant=variant,
    )


def _row_zero() -> tuple[PhysicalKey, ...]:
    fixed = tuple(
        _key(f"r0_{key_id}_1u", label, 0, float(index))
        for index, (key_id, label) in enumerate(
            (
                ("esc", "Esc"),
                ("1", "1"),
                ("2", "2"),
                ("3", "3"),
                ("4", "4"),
                ("5", "5"),
                ("6", "6"),
                ("7", "7"),
                ("8", "8"),
                ("9", "9"),
                ("0", "0"),
                ("minus", "-"),
                ("equal", "="),
            )
        )
    )
    return fixed + (
        _key(
            "r0_top_2u",
            "Top 2u",
            0,
            13.0,
            2.0,
            region="top-right",
            variant="wide",
        ),
        _key(
            "r0_top_split_left_fn_1u",
            "Top split Fn",
            0,
            13.0,
            region="top-right",
            variant="split-left",
        ),
        _key(
            "r0_top_split_right_1u",
            "Top split right",
            0,
            14.0,
            logical_node_id="r0_top_2u",
            region="top-right",
            variant="split-right",
        ),
    )


def _row_one() -> tuple[PhysicalKey, ...]:
    middle = tuple(
        _key(f"r1_{key_id}_1u", label, 1, 1.5 + index)
        for index, (key_id, label) in enumerate(
            (
                ("q", "Q"),
                ("w", "W"),
                ("e", "E"),
                ("r", "R"),
                ("t", "T"),
                ("y", "Y"),
                ("u", "U"),
                ("i", "I"),
                ("o", "O"),
                ("p", "P"),
                ("left_bracket", "["),
                ("right_bracket", "]"),
            )
        )
    )
    return (
        _key("r1_tab_1.5u", "Tab", 1, 0.0, 1.5),
        *middle,
        _key("r1_backslash_1.5u", "\\", 1, 13.5, 1.5),
    )


def _row_two() -> tuple[PhysicalKey, ...]:
    middle = tuple(
        _key(f"r2_{key_id}_1u", label, 2, 1.75 + index)
        for index, (key_id, label) in enumerate(
            (
                ("a", "A"),
                ("s", "S"),
                ("d", "D"),
                ("f", "F"),
                ("g", "G"),
                ("h", "H"),
                ("j", "J"),
                ("k", "K"),
                ("l", "L"),
                ("semicolon", ";"),
                ("quote", "'"),
            )
        )
    )
    return (
        _key("r2_caps_1.75u", "Caps", 2, 0.0, 1.75),
        *middle,
        _key(
            "r2_enter_ansi_2.25u",
            "ANSI Enter",
            2,
            12.75,
            2.25,
            region="enter",
            variant="wide",
        ),
        _key(
            "r2_enter_split_left_fn_1u",
            "Enter split Fn",
            2,
            12.75,
            region="enter",
            variant="split-left",
        ),
        _key(
            "r2_enter_split_right_1.25u",
            "Split Enter",
            2,
            13.75,
            1.25,
            logical_node_id="r2_enter_ansi_2.25u",
            region="enter",
            variant="split-right",
        ),
    )


def _row_three() -> tuple[PhysicalKey, ...]:
    middle = tuple(
        _key(f"r3_{key_id}_1u", label, 3, 2.25 + index)
        for index, (key_id, label) in enumerate(
            (
                ("z", "Z"),
                ("x", "X"),
                ("c", "C"),
                ("v", "V"),
                ("b", "B"),
                ("n", "N"),
                ("m", "M"),
                ("comma", ","),
                ("period", "."),
                ("slash", "/"),
            )
        )
    )
    return (
        _key(
            "r3_lshift_split_left_fn_1u",
            "LShift split Fn",
            3,
            0.0,
            region="lshift",
            variant="split-left",
        ),
        _key(
            "r3_lshift_2.25u",
            "LShift",
            3,
            0.0,
            2.25,
            region="lshift",
            variant="wide",
        ),
        _key(
            "r3_lshift_split_1.25u",
            "Split LShift",
            3,
            1.0,
            1.25,
            logical_node_id="r3_lshift_2.25u",
            region="lshift",
            variant="split-right",
        ),
        *middle,
        _key(
            "r3_rshift_left_1.75u",
            "Left split RShift",
            3,
            12.25,
            1.75,
            logical_node_id="r3_rshift_1.75u",
            region="rshift",
            variant="split-left-shift",
        ),
        _key(
            "r3_rshift_right_fn_1u",
            "Right split Fn",
            3,
            14.0,
            logical_node_id="r3_rshift_left_fn_1u",
            region="rshift",
            variant="split-right-fn",
        ),
        _key(
            "r3_rshift_left_fn_1u",
            "Left split Fn",
            3,
            12.25,
            region="rshift",
            variant="split-left-fn",
        ),
        _key(
            "r3_rshift_right_1.75u",
            "Right split RShift",
            3,
            13.25,
            1.75,
            logical_node_id="r3_rshift_1.75u",
            region="rshift",
            variant="split-right-shift",
        ),
    )


def _row_four() -> tuple[PhysicalKey, ...]:
    definitions = (
        ("r4_left_ctrl_1.25u", "Left Ctrl", 0.0, 1.25),
        ("r4_left_win_1.25u", "Left Win", 1.25, 1.25),
        ("r4_left_alt_1.25u", "Left Alt", 2.5, 1.25),
        ("r4_space_2.25u", "Space", 3.75, 2.25),
        ("r4_fn_1u", "Fn", 6.0, 1.0),
        ("r4_left_1u", "Left", 7.0, 1.0),
        ("r4_down_1u", "Down", 8.0, 1.0),
        ("r4_up_1u", "Up", 9.0, 1.0),
        ("r4_right_1u", "Right", 10.0, 1.0),
        ("r4_right_fn_1u", "Right Fn", 11.0, 1.0),
        ("r4_right_alt_1u", "Right Alt", 12.0, 1.0),
        ("r4_right_win_1u", "Right Win", 13.0, 1.0),
        ("r4_right_ctrl_1u", "Right Ctrl", 14.0, 1.0),
    )
    return tuple(
        _key(physical_key_id, label, 4, x_u, width_u)
        for physical_key_id, label, x_u, width_u in definitions
    )


def physical_keys() -> tuple[PhysicalKey, ...]:
    return _row_zero() + _row_one() + _row_two() + _row_three() + _row_four()
