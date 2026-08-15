from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.update_socket_library import ALL_NAMES, McpClient


def coupon_plan() -> dict[str, list[dict[str, Any]]]:
    clean = [
        {
            "footprint": f"lh60-sockets:{name}",
            "reference": f"SW_CLEAN_{index + 1}",
            "x": 20.0 + (index % 4) * 35.0,
            "y": 20.0 + (index // 4) * 35.0,
            "rotation": 0.0,
            "layer": "F.Cu",
        }
        for index, name in enumerate(ALL_NAMES)
    ]
    conflict = [
        {
            "footprint": "lh60-sockets:Gateron-LP-Hotswap-Socket-1U",
            "reference": "SW_CONFLICT_1",
            "x": 25.0,
            "y": 30.0,
            "rotation": 0.0,
            "layer": "F.Cu",
        },
        {
            "footprint": "lh60-sockets:Gateron-LP-Hotswap-Socket-1U",
            "reference": "SW_CONFLICT_2",
            "x": 42.25,
            "y": 30.0,
            "rotation": 0.0,
            "layer": "F.Cu",
        },
    ]
    return {"clean": clean, "conflict": conflict}


def coupon_specs() -> dict[str, dict[str, Any]]:
    plan = coupon_plan()
    return {
        "socket-clean": {
            "width": 145.0,
            "height": 75.0,
            "placements": plan["clean"],
        },
        "socket-conflicts": {
            "width": 80.0,
            "height": 60.0,
            "placements": plan["conflict"],
        },
    }


def target_paths(output_dir: Path, name: str) -> tuple[Path, Path, Path]:
    return (
        output_dir / f"{name}.kicad_pro",
        output_dir / f"{name}.kicad_sch",
        output_dir / f"{name}.kicad_pcb",
    )


def generate(
    client: McpClient,
    output_dir: Path,
    footprint_library: Path,
) -> None:
    client.call_tool(
        "load_toolset",
        {"name": ["project", "pcb_board", "pcb_components", "library"]},
    )
    for name, spec in coupon_specs().items():
        project, schematic, board = target_paths(output_dir, name)
        existing = [path for path in (project, schematic, board) if path.exists()]
        if existing:
            joined = ", ".join(str(path) for path in existing)
            raise RuntimeError(f"refusing to replace existing coupon files: {joined}")

        client.call_tool(
            "create_project",
            {"path": str(output_dir), "name": name},
        )
        client.call_tool(
            "set_board_size",
            {
                "board": str(board),
                "width": spec["width"],
                "height": spec["height"],
                "origin_x": 0.0,
                "origin_y": 0.0,
            },
        )
        client.call_tool(
            "register_footprint_library",
            {
                "library_path": str(footprint_library),
                "nickname": "lh60-sockets",
                "scope": "project",
                "project": str(project),
                "replace_existing": True,
            },
        )
        for placement in spec["placements"]:
            client.call_tool(
                "place_component",
                {"board": str(board), **placement},
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate LH60 clean and expected-conflict coupon boards through Konnect MCP."
    )
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "test",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the deterministic coupon plan without writing files.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create coupon projects and place footprints through Konnect MCP.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.plan:
        print(json.dumps(coupon_specs(), indent=2, sort_keys=True))
        return 0
    if not args.apply:
        print("choose --plan or --apply", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    with McpClient(args.konnect, args.config) as client:
        generate(client, args.output_dir, ROOT / "lib" / "lh60-sockets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
