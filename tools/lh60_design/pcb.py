from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from tools.lh60_design.layout import physical_keys
from tools.lh60_design.mcp import McpClient
from tools.lh60_design.schematic import switch_references


ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "lh60.kicad_pcb"
REGION_REPORTS = ROOT / "docs" / "regions"
REVIEWED_ROTATION_OVERRIDES_DEG = {
    "r0_top_split_left_fn_1u": 0.0,
    "r2_enter_ansi_2.25u": 180.0,
    "r2_enter_split_left_fn_1u": 0.0,
    "r2_enter_split_right_1.25u": 0.0,
    "r3_lshift_split_left_fn_1u": 0.0,
    "r3_lshift_2.25u": 180.0,
    "r3_lshift_split_1.25u": 0.0,
}


@dataclass(frozen=True)
class FootprintPlacement:
    physical_key_id: str
    reference: str
    x_mm: float
    y_mm: float
    rotation_deg: float
    layer: str = "F.Cu"


def _balanced_block(source: str, start: int) -> tuple[int, int]:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(source)):
        character = source[index]
        if escaped:
            escaped = False
        elif in_string:
            if character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise ValueError(f"unbalanced S-expression starting at byte {start}")


def _direct_footprint_blocks(source: str) -> tuple[str, ...]:
    blocks = []
    depth = 0
    in_string = False
    escaped = False
    index = 0
    while index < len(source):
        character = source[index]
        if escaped:
            escaped = False
        elif in_string:
            if character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == "(":
            if depth == 1 and source.startswith("(footprint", index):
                start, end = _balanced_block(source, index)
                blocks.append(source[start:end])
                index = end
                continue
            depth += 1
        elif character == ")":
            depth -= 1
        index += 1
    return tuple(blocks)


def _root_tag_block(source: str, tag: str) -> str:
    marker = f"({tag}"
    for start in range(len(source)):
        if not source.startswith(marker, start):
            continue
        prefix = source[start + len(marker) : start + len(marker) + 1]
        if prefix not in {" ", "\t", "\r", "\n", ")"}:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index, character in enumerate(source[:start]):
            if escaped:
                escaped = False
            elif in_string:
                if character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
            elif character == '"':
                in_string = True
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
        if depth == 1:
            block_start, block_end = _balanced_block(source, start)
            return source[block_start:block_end]
    raise ValueError(f"missing root ({tag} ...) block")


def read_board_placements(
    board: Path | str = BOARD,
) -> dict[str, tuple[float, float, float, str]]:
    source = Path(board).read_text()
    placements = {}
    for block in _direct_footprint_blocks(source):
        reference_marker = '(property "Reference" "'
        reference_start = block.find(reference_marker)
        if reference_start < 0:
            continue
        reference_start += len(reference_marker)
        reference_end = block.find('"', reference_start)
        reference = block[reference_start:reference_end]
        at_tokens = _root_tag_block(block, "at")[1:-1].split()
        layer_block = _root_tag_block(block, "layer")
        layer = layer_block.split('"', 2)[1]
        placements[reference] = (
            float(at_tokens[1]),
            float(at_tokens[2]),
            float(at_tokens[3]) if len(at_tokens) > 3 else 0.0,
            layer,
        )
    return placements


def _region_rotations() -> dict[str, float]:
    rotations: dict[str, float] = {}
    for report_path in sorted(REGION_REPORTS.glob("*.json")):
        report = json.loads(report_path.read_text())
        for placement in report["placements"]:
            physical_key_id = placement["socket_ref"]
            if physical_key_id in rotations:
                raise ValueError(
                    f"duplicate regional placement for {physical_key_id}"
                )
            rotations[physical_key_id] = float(placement["rotation_deg"])
    return rotations


def socket_placement_plan() -> tuple[FootprintPlacement, ...]:
    references = switch_references()
    rotations = _region_rotations()
    rotations.update(REVIEWED_ROTATION_OVERRIDES_DEG)
    keys = physical_keys()
    regional_key_ids = {
        key.physical_key_id for key in keys if key.region is not None
    }
    if set(rotations) != regional_key_ids:
        missing = sorted(regional_key_ids - set(rotations))
        extra = sorted(set(rotations) - regional_key_ids)
        raise ValueError(
            f"regional placement reports do not match layout: missing={missing}, extra={extra}"
        )

    return tuple(
        FootprintPlacement(
            physical_key_id=key.physical_key_id,
            reference=references[key.physical_key_id],
            x_mm=key.center_x_mm,
            y_mm=key.center_y_mm,
            rotation_deg=rotations.get(key.physical_key_id, 0.0),
        )
        for key in keys
    )


def apply_socket_placements(client: McpClient, board: Path | str = BOARD) -> None:
    board_path = str(board)
    schemas = client.tool_schemas("pcb_components")
    missing = {"move_component", "rotate_component"} - set(schemas)
    if missing:
        raise RuntimeError(
            f"Konnect pcb_components is missing required tools: {sorted(missing)}"
        )
    for placement in socket_placement_plan():
        client.call_tool(
            "move_component",
            {
                "board": board_path,
                "reference": placement.reference,
                "x": placement.x_mm,
                "y": placement.y_mm,
            },
        )
        client.call_tool(
            "rotate_component",
            {
                "board": board_path,
                "reference": placement.reference,
                "rotation": placement.rotation_deg,
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place all LH60 production sockets through Konnect."
    )
    parser.add_argument("--board", type=Path, default=BOARD)
    parser.add_argument(
        "--konnect",
        type=Path,
        default=Path.home() / ".local/bin/konnect",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".config/konnect/config.toml",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with McpClient(args.konnect, args.config) as client:
        apply_socket_placements(client, args.board)


if __name__ == "__main__":
    main()
