from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from tools.lh60_design.mcp import McpClient


ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = ROOT / "lib" / "lh60-core"
SYMBOL_LIBRARY = LIBRARY_ROOT / "lh60-core.kicad_sym"
FOOTPRINT_LIBRARY = LIBRARY_ROOT / "lh60-core.pretty"
PROJECT = ROOT / "lh60.kicad_pro"
RETIRED_SYMBOLS = ("KeySwitch", "MatrixDiode")


@dataclass(frozen=True)
class CorePinSpec:
    number: str
    name: str
    pin_type: str
    x: float
    y: float
    angle: float


@dataclass(frozen=True)
class CoreSymbolSpec:
    name: str
    reference_prefix: str
    value: str
    pins: tuple[CorePinSpec, ...]


@dataclass(frozen=True)
class CorePadSpec:
    number: str
    shape: str
    x: float
    y: float
    width: float
    height: float
    layers: tuple[str, ...]
    paste: bool


@dataclass(frozen=True)
class CoreFootprintSpec:
    name: str
    description: str
    pads: tuple[CorePadSpec, ...]
    body_width_mm: float
    body_height_mm: float
    courtyard_clearance_mm: float
    attributes: tuple[str, ...]


def _horizontal_pins(
    left_number: str,
    left_name: str,
    right_number: str,
    right_name: str,
) -> tuple[CorePinSpec, ...]:
    return (
        CorePinSpec(left_number, left_name, "passive", -5.08, 0.0, 0.0),
        CorePinSpec(right_number, right_name, "passive", 5.08, 0.0, 180.0),
    )


def core_symbol_specs() -> tuple[CoreSymbolSpec, ...]:
    return (
        CoreSymbolSpec(
            name="TestPoint",
            reference_prefix="TP",
            value="TestPoint",
            pins=(
                CorePinSpec("1", "TP", "passive", 5.08, 0.0, 180.0),
            ),
        ),
        CoreSymbolSpec(
            name="PowerFlag",
            reference_prefix="#FLG",
            value="PWR_FLAG",
            pins=(
                CorePinSpec("1", "PWR_FLAG", "power_out", 5.08, 0.0, 180.0),
            ),
        ),
    )


def core_footprint_specs() -> tuple[CoreFootprintSpec, ...]:
    return (
        CoreFootprintSpec(
            name="D_SOD-323_Bottom",
            description=(
                "SOD-323 diode on bottom side; pad geometry derived from "
                "KiCad D_SOD-323"
            ),
            pads=(
                CorePadSpec(
                    "1",
                    "rect",
                    -1.05,
                    0.0,
                    0.6,
                    0.45,
                    ("F.Cu", "F.Paste", "F.Mask"),
                    True,
                ),
                CorePadSpec(
                    "2",
                    "rect",
                    1.05,
                    0.0,
                    0.6,
                    0.45,
                    ("F.Cu", "F.Paste", "F.Mask"),
                    True,
                ),
            ),
            body_width_mm=1.8,
            body_height_mm=1.4,
            courtyard_clearance_mm=0.25,
            attributes=("smd",),
        ),
        CoreFootprintSpec(
            name="TestPoint_Pad_D1.5mm_Bottom",
            description=(
                "Bottom-side 1.5mm SMD test pad derived from KiCad "
                "TestPoint_Pad_D1.5mm"
            ),
            pads=(
                CorePadSpec(
                    "1",
                    "circle",
                    0.0,
                    0.0,
                    1.5,
                    1.5,
                    ("F.Cu", "F.Mask"),
                    False,
                ),
            ),
            body_width_mm=1.5,
            body_height_mm=1.5,
            courtyard_clearance_mm=0.5,
            attributes=("exclude_from_pos_files", "exclude_from_bom"),
        ),
    )


def _symbol_definition_count(symbol_name: str) -> int:
    if not SYMBOL_LIBRARY.exists():
        return 0
    pattern = re.compile(
        rf'(?m)^  \(symbol "{re.escape(symbol_name)}"$'
    )
    return len(pattern.findall(SYMBOL_LIBRARY.read_text()))


def _symbol_payload(spec: CoreSymbolSpec) -> dict[str, object]:
    return {
        "library_path": str(SYMBOL_LIBRARY),
        "name": spec.name,
        "reference_prefix": spec.reference_prefix,
        "value": spec.value,
        "show_pin_names": True,
        "show_pin_numbers": True,
        "pins": [
            {
                "number": pin.number,
                "name": pin.name,
                "type": pin.pin_type,
                "x": pin.x,
                "y": pin.y,
                "angle": pin.angle,
                "length": 2.54,
            }
            for pin in spec.pins
        ],
    }


def _footprint_payload(spec: CoreFootprintSpec) -> dict[str, object]:
    return {
        "output": str(FOOTPRINT_LIBRARY / f"{spec.name}.kicad_mod"),
        "name": spec.name,
        "description": spec.description,
        "body_width": spec.body_width_mm,
        "body_height": spec.body_height_mm,
        "courtyard_clearance": spec.courtyard_clearance_mm,
        "pads": [
            {
                "number": pad.number,
                "type": "smd",
                "shape": pad.shape,
                "x": pad.x,
                "y": pad.y,
                "width": pad.width,
                "height": pad.height,
                "layers": list(pad.layers),
            }
            for pad in spec.pads
        ],
    }


def _replace_graphics(
    client: McpClient,
    footprint: Path,
    layer: str,
    graphics: list[dict[str, object]],
) -> None:
    client.call_tool(
        "set_footprint_graphics",
        {
            "footprint_path": str(footprint),
            "selector": {"layer": layer},
            "mode": "replace",
            "graphics": graphics,
        },
    )


def _delete_graphics(client: McpClient, footprint: Path, layer: str) -> None:
    client.call_tool(
        "set_footprint_graphics",
        {
            "footprint_path": str(footprint),
            "selector": {"layer": layer},
            "mode": "delete",
        },
    )


def _apply_diode_graphics(client: McpClient, footprint: Path) -> None:
    fab = [
        {
            "type": "rect",
            "start": {"x": -0.9, "y": -0.7},
            "end": {"x": 0.9, "y": 0.7},
            "stroke_width_mm": 0.1,
            "fill": "none",
        },
        {
            "type": "line",
            "start": {"x": -0.3, "y": -0.35},
            "end": {"x": -0.3, "y": 0.35},
            "stroke_width_mm": 0.1,
        },
        {
            "type": "line",
            "start": {"x": 0.2, "y": -0.35},
            "end": {"x": 0.2, "y": 0.35},
            "stroke_width_mm": 0.1,
        },
        {
            "type": "line",
            "start": {"x": -0.3, "y": 0.0},
            "end": {"x": 0.2, "y": -0.35},
            "stroke_width_mm": 0.1,
        },
        {
            "type": "line",
            "start": {"x": -0.3, "y": 0.0},
            "end": {"x": 0.2, "y": 0.35},
            "stroke_width_mm": 0.1,
        },
    ]
    _replace_graphics(client, footprint, "F.Fab", fab)
    _replace_graphics(
        client,
        footprint,
        "F.CrtYd",
        [
            {
                "type": "rect",
                "start": {"x": -1.6, "y": -0.95},
                "end": {"x": 1.6, "y": 0.95},
                "stroke_width_mm": 0.05,
                "fill": "none",
            }
        ],
    )
    _replace_graphics(
        client,
        footprint,
        "F.SilkS",
        [
            {
                "type": "line",
                "start": {"x": -1.5, "y": -0.85},
                "end": {"x": -1.5, "y": 0.85},
                "stroke_width_mm": 0.12,
            },
            {
                "type": "line",
                "start": {"x": -1.5, "y": -0.85},
                "end": {"x": 1.05, "y": -0.85},
                "stroke_width_mm": 0.12,
            },
            {
                "type": "line",
                "start": {"x": -1.5, "y": 0.85},
                "end": {"x": 1.05, "y": 0.85},
                "stroke_width_mm": 0.12,
            },
        ],
    )


def _apply_test_point_graphics(client: McpClient, footprint: Path) -> None:
    _replace_graphics(
        client,
        footprint,
        "F.Fab",
        [
            {
                "type": "circle",
                "center": {"x": 0.0, "y": 0.0},
                "radius_mm": 0.75,
                "stroke_width_mm": 0.1,
                "fill": "none",
            }
        ],
    )
    _replace_graphics(
        client,
        footprint,
        "F.CrtYd",
        [
            {
                "type": "circle",
                "center": {"x": 0.0, "y": 0.0},
                "radius_mm": 1.25,
                "stroke_width_mm": 0.05,
                "fill": "none",
            }
        ],
    )


def apply_core_library(client: McpClient) -> None:
    client.tool_schemas("library")
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    FOOTPRINT_LIBRARY.mkdir(parents=True, exist_ok=True)

    for symbol_name in RETIRED_SYMBOLS:
        for _ in range(_symbol_definition_count(symbol_name)):
            client.call_tool(
                "delete_symbol",
                {
                    "library_path": str(SYMBOL_LIBRARY),
                    "symbol_name": symbol_name,
                },
            )

    for symbol in core_symbol_specs():
        for _ in range(_symbol_definition_count(symbol.name)):
            client.call_tool(
                "delete_symbol",
                {
                    "library_path": str(SYMBOL_LIBRARY),
                    "symbol_name": symbol.name,
                },
            )
        client.call_tool("create_symbol", _symbol_payload(symbol))

    for spec in core_footprint_specs():
        footprint = FOOTPRINT_LIBRARY / f"{spec.name}.kicad_mod"
        client.call_tool("create_footprint", _footprint_payload(spec))
        if spec.name == "D_SOD-323_Bottom":
            _apply_diode_graphics(client, footprint)
        else:
            _apply_test_point_graphics(client, footprint)
        client.call_tool(
            "set_footprint_metadata",
            {
                "footprint_path": str(footprint),
                "description": spec.description,
                "tags": ["lh60", "bottom_side"],
                "attributes": list(spec.attributes),
            },
        )

    client.call_tool(
        "register_symbol_library",
        {
            "library_path": str(SYMBOL_LIBRARY),
            "nickname": "lh60-core",
            "project": str(PROJECT),
            "scope": "project",
        },
    )
    client.call_tool(
        "register_footprint_library",
        {
            "library_path": str(FOOTPRINT_LIBRARY),
            "nickname": "lh60-core",
            "project": str(PROJECT),
            "scope": "project",
            "replace_existing": True,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the LH60 core schematic and footprint library through Konnect."
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
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.apply:
        print("choose --apply", file=sys.stderr)
        return 2
    with McpClient(args.konnect, args.config) as client:
        apply_core_library(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
