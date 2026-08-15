from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tools.lh60_design.mcp import McpClient


PROJECT_NAME = "lh60"
BOARD_WIDTH_MM = 285.75
BOARD_HEIGHT_MM = 95.25
MIN_CLEARANCE_MM = 0.25
MIN_TRACE_WIDTH_MM = 0.25
MIN_HOLE_TO_HOLE_MM = 0.45
MIN_VIA_DRILL_MM = 0.30
MIN_VIA_SIZE_MM = 0.70


def _project_paths(project_dir: Path) -> tuple[Path, Path, Path]:
    return (
        project_dir / f"{PROJECT_NAME}.kicad_pro",
        project_dir / f"{PROJECT_NAME}.kicad_sch",
        project_dir / f"{PROJECT_NAME}.kicad_pcb",
    )


def _validate_project_state(project_dir: Path) -> bool:
    project_files = _project_paths(project_dir)
    existing = tuple(path.exists() for path in project_files)
    if any(existing) and not all(existing):
        present = ", ".join(
            path.name for path, exists in zip(project_files, existing) if exists
        )
        raise RuntimeError(f"partial existing project: {present}")
    return all(existing)


def create_production_project(client: McpClient, project_dir: Path) -> None:
    project_dir = project_dir.resolve()
    project, _, board = _project_paths(project_dir)
    project_exists = _validate_project_state(project_dir)

    socket_library = project_dir / "lib" / "lh60-sockets"
    mcu_root = project_dir / "lib" / "lh60-mcu"
    mcu_footprints = mcu_root / "lh60-mcu.pretty"
    mcu_symbols = mcu_root / "lh60-mcu.kicad_sym"
    required_libraries = (socket_library, mcu_footprints, mcu_symbols)
    missing = [path for path in required_libraries if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"required project libraries are missing: {missing_text}")

    if not project_exists:
        client.call_tool(
            "create_project",
            {"path": str(project_dir), "name": PROJECT_NAME},
        )

    client.tool_schemas("library")
    client.call_tool(
        "register_footprint_library",
        {
            "library_path": str(socket_library),
            "nickname": "lh60-sockets",
            "project": str(project),
            "scope": "project",
            "replace_existing": True,
        },
    )
    client.call_tool(
        "register_footprint_library",
        {
            "library_path": str(mcu_footprints),
            "nickname": "lh60-mcu",
            "project": str(project),
            "scope": "project",
            "replace_existing": True,
        },
    )
    client.call_tool(
        "register_symbol_library",
        {
            "library_path": str(mcu_symbols),
            "nickname": "lh60-mcu",
            "project": str(project),
            "scope": "project",
        },
    )

    client.tool_schemas("verification")
    client.call_tool(
        "set_design_rules",
        {
            "board": str(board),
            "min_clearance": MIN_CLEARANCE_MM,
            "min_trace_width": MIN_TRACE_WIDTH_MM,
            "min_hole_to_hole": MIN_HOLE_TO_HOLE_MM,
            "min_via_drill": MIN_VIA_DRILL_MM,
            "min_via_size": MIN_VIA_SIZE_MM,
        },
    )
    for layer in ("F.Cu", "B.Cu"):
        client.call_tool(
            "set_layer_constraints",
            {
                "board": str(board),
                "layer": layer,
                "min_clearance": MIN_CLEARANCE_MM,
                "min_trace_width": MIN_TRACE_WIDTH_MM,
            },
        )

    client.tool_schemas("pcb_board")
    client.call_tool(
        "set_board_size",
        {
            "board": str(board),
            "width": BOARD_WIDTH_MM,
            "height": BOARD_HEIGHT_MM,
            "origin_x": 0.0,
            "origin_y": 0.0,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or converge the blank LH60 production project through Konnect."
    )
    parser.add_argument("project_dir", type=Path)
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
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.apply:
        print("choose --apply", file=sys.stderr)
        return 2
    with McpClient(args.konnect, args.config) as client:
        create_production_project(client, args.project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
