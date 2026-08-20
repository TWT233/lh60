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
    pad_type: str
    shape: str
    x: float
    y: float
    width: float
    height: float
    layers: tuple[str, ...]
    drill_mm: float | None = None
    roundrect_rratio: float | None = None


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


def _vertical_connector_pins(count: int) -> tuple[CorePinSpec, ...]:
    return tuple(
        CorePinSpec(str(index), str(index), "passive", -5.08, (index - 1) * 2.54, 0.0)
        for index in range(1, count + 1)
    )


def _connector_symbol_spec(count: int) -> CoreSymbolSpec:
    name = f"Conn_01x0{count}"
    return CoreSymbolSpec(
        name=name,
        reference_prefix="J",
        value=name,
        pins=_vertical_connector_pins(count),
    )


def _connector_footprint_spec(count: int) -> CoreFootprintSpec:
    return CoreFootprintSpec(
        name=f"PinHeader_1x0{count}_P2.54mm_Vertical",
        description=(
            f"{count}-pin 2.54 mm vertical THT pin header; canonical front-side "
            "library definition for hand soldering, excluded from pick-and-place, "
            "retained in the BOM"
        ),
        pads=tuple(
            CorePadSpec(
                number=str(index),
                pad_type="thru_hole",
                shape="rect" if index == 1 else "circle",
                x=0.0,
                y=(index - 1) * 2.54,
                width=1.7,
                height=1.7,
                layers=("*.Cu", "*.Mask"),
                drill_mm=1.0,
            )
            for index in range(1, count + 1)
        ),
        body_width_mm=2.54,
        body_height_mm=count * 2.54,
        courtyard_clearance_mm=0.5,
        attributes=("exclude_from_pos_files",),
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
        _connector_symbol_spec(3),
        _connector_symbol_spec(4),
        _connector_symbol_spec(5),
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
                    number="1",
                    pad_type="smd",
                    shape="rect",
                    x=-1.05,
                    y=0.0,
                    width=0.6,
                    height=0.45,
                    layers=("F.Cu", "F.Paste", "F.Mask"),
                ),
                CorePadSpec(
                    number="2",
                    pad_type="smd",
                    shape="rect",
                    x=1.05,
                    y=0.0,
                    width=0.6,
                    height=0.45,
                    layers=("F.Cu", "F.Paste", "F.Mask"),
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
                    number="1",
                    pad_type="smd",
                    shape="circle",
                    x=0.0,
                    y=0.0,
                    width=1.5,
                    height=1.5,
                    layers=("F.Cu", "F.Mask"),
                ),
            ),
            body_width_mm=1.5,
            body_height_mm=1.5,
            courtyard_clearance_mm=0.5,
            attributes=("exclude_from_pos_files", "exclude_from_bom"),
        ),
        _connector_footprint_spec(3),
        _connector_footprint_spec(4),
        _connector_footprint_spec(5),
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
    pads: list[dict[str, object]] = []
    for pad in spec.pads:
        payload: dict[str, object] = {
            "number": pad.number,
            "type": pad.pad_type,
            "shape": pad.shape,
            "x": pad.x,
            "y": pad.y,
            "width": pad.width,
            "height": pad.height,
            "layers": list(pad.layers),
        }
        if pad.drill_mm is not None:
            payload["drill"] = pad.drill_mm
        if pad.roundrect_rratio is not None:
            payload["roundrect_rratio"] = pad.roundrect_rratio
        pads.append(payload)
    return {
        "output": str(FOOTPRINT_LIBRARY / f"{spec.name}.kicad_mod"),
        "name": spec.name,
        "description": spec.description,
        "body_width": spec.body_width_mm,
        "body_height": spec.body_height_mm,
        "courtyard_clearance": spec.courtyard_clearance_mm,
        "pads": pads,
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


def _connector_graphics(pin_count: int) -> dict[str, list[dict[str, object]]]:
    bottom_y = (pin_count - 1) * 2.54 + 1.27
    return {
        "F.Fab": [
            {
                "type": "rect",
                "start": {"x": -1.27, "y": -1.27},
                "end": {"x": 1.27, "y": bottom_y},
                "stroke_width_mm": 0.1,
                "fill": "none",
            },
        ],
        "F.CrtYd": [
            {
                "type": "rect",
                "start": {"x": -1.77, "y": -1.77},
                "end": {"x": 1.77, "y": bottom_y + 0.5},
                "stroke_width_mm": 0.05,
                "fill": "none",
            },
        ],
        "F.SilkS": [
            {
                "type": "line",
                "start": {"x": -1.52, "y": -1.52},
                "end": {"x": 1.52, "y": -1.52},
                "stroke_width_mm": 0.15,
            },
            {
                "type": "line",
                "start": {"x": -1.52, "y": bottom_y + 0.25},
                "end": {"x": 1.52, "y": bottom_y + 0.25},
                "stroke_width_mm": 0.15,
            },
            {
                "type": "line",
                "start": {"x": -1.52, "y": -1.52},
                "end": {"x": -1.52, "y": bottom_y + 0.25},
                "stroke_width_mm": 0.15,
            },
            {
                "type": "line",
                "start": {"x": 1.52, "y": -1.52},
                "end": {"x": 1.52, "y": bottom_y + 0.25},
                "stroke_width_mm": 0.15,
            },
            {
                "type": "line",
                "start": {"x": -2.3, "y": -1.52},
                "end": {"x": -1.52, "y": -1.52},
                "stroke_width_mm": 0.15,
            },
            {
                "type": "line",
                "start": {"x": -2.3, "y": -1.52},
                "end": {"x": -2.3, "y": 0.8},
                "stroke_width_mm": 0.15,
            },
        ],
    }


def _apply_connector_graphics(client: McpClient, footprint: Path, pin_count: int) -> None:
    for layer, graphics in _connector_graphics(pin_count).items():
        _replace_graphics(client, footprint, layer, graphics)


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
            tags = ["lh60", "bottom_side"]
        else:
            if spec.name == "TestPoint_Pad_D1.5mm_Bottom":
                _apply_test_point_graphics(client, footprint)
                tags = ["lh60", "bottom_side"]
            else:
                pin_count = int(spec.name.split("_")[1][2:])
                _apply_connector_graphics(client, footprint, pin_count)
                tags = ["lh60", "pin_header", "through_hole"]
        client.call_tool(
            "set_footprint_metadata",
            {
                "footprint_path": str(footprint),
                "description": spec.description,
                "tags": tags,
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
