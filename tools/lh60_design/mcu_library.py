from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from tools.lh60_design.mcp import McpClient


ROOT = Path(__file__).resolve().parents[2]
MCU_ROOT = ROOT / "lib" / "lh60-mcu"
SYMBOL_LIBRARY = MCU_ROOT / "lh60-mcu.kicad_sym"
FOOTPRINT_LIBRARY = MCU_ROOT / "lh60-mcu.pretty"
FOOTPRINT_PATH = FOOTPRINT_LIBRARY / "MCU_RP2040-Tiny_SMD.kicad_mod"
MODEL_PATH = MCU_ROOT / "RP2040-Tiny-V1.1.step"


@dataclass(frozen=True)
class SymbolPinSpec:
    number: str
    name: str
    pin_type: str
    x: float
    y: float
    angle: float


@dataclass(frozen=True)
class McuPadSpec:
    number: str
    x: float
    y: float
    width: float = 2.4
    height: float = 1.6
    rotation: float = 0.0


@dataclass(frozen=True)
class McuFootprintSpec:
    name: str
    pads: tuple[McuPadSpec, ...]
    body_width_mm: float
    body_height_mm: float
    courtyard_clearance_mm: float
    fpc_edge: str


def rp2040_tiny_symbol_pins() -> tuple[SymbolPinSpec, ...]:
    pins: list[SymbolPinSpec] = []
    for index in range(9):
        pins.append(
            SymbolPinSpec(
                number=str(index + 1),
                name=f"GP{index}",
                pin_type="bidirectional",
                x=15.24,
                y=10.16 - index * 2.54,
                angle=180.0,
            )
        )
    for index in range(5):
        pins.append(
            SymbolPinSpec(
                number=str(index + 10),
                name=f"GP{index + 9}",
                pin_type="bidirectional",
                x=5.08 - index * 2.54,
                y=-15.24,
                angle=90.0,
            )
        )
    left_names = (
        ("15", "GP14", "bidirectional"),
        ("16", "GP15", "bidirectional"),
        ("17", "GP26", "bidirectional"),
        ("18", "GP27", "bidirectional"),
        ("19", "GP28", "bidirectional"),
        ("20", "GP29", "bidirectional"),
        ("21", "3V3", "power_in"),
        ("22", "GND", "power_in"),
        ("23", "VSYS", "power_in"),
    )
    for index, (number, name, pin_type) in enumerate(left_names):
        pins.append(
            SymbolPinSpec(
                number=number,
                name=name,
                pin_type=pin_type,
                x=-15.24,
                y=-10.16 + index * 2.54,
                angle=0.0,
            )
        )
    return tuple(pins)


def rp2040_tiny_footprint_spec() -> McuFootprintSpec:
    pads: list[McuPadSpec] = []
    for index in range(9):
        pads.append(
            McuPadSpec(
                number=str(index + 1),
                x=8.2,
                y=index * 2.54,
                rotation=180.0 if index == 0 else 0.0,
            )
        )
    for index in range(5):
        pads.append(
            McuPadSpec(
                number=str(index + 10),
                x=5.08 - index * 2.54,
                y=20.9,
                rotation=90.0,
            )
        )
    for index in range(9):
        pads.append(
            McuPadSpec(
                number=str(index + 15),
                x=-8.2,
                y=20.32 - index * 2.54,
            )
        )
    return McuFootprintSpec(
        name="MCU_RP2040-Tiny_SMD",
        pads=tuple(pads),
        body_width_mm=18.0,
        body_height_mm=23.5,
        courtyard_clearance_mm=0.5,
        fpc_edge="rear",
    )


def symbol_payload() -> dict[str, object]:
    return {
        "library_path": str(SYMBOL_LIBRARY),
        "name": "RP2040-Tiny",
        "reference_prefix": "U",
        "value": "RP2040-Tiny",
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
            for pin in rp2040_tiny_symbol_pins()
        ],
    }


def footprint_payload() -> dict[str, object]:
    spec = rp2040_tiny_footprint_spec()
    return {
        "output": str(FOOTPRINT_PATH),
        "name": spec.name,
        "description": (
            "Waveshare RP2040-Tiny SMD castellated module, "
            "18x23.5mm body, FPC connector at rear edge"
        ),
        "body_width": spec.body_width_mm,
        "body_height": spec.body_height_mm,
        "courtyard_clearance": spec.courtyard_clearance_mm,
        "pads": [
            {
                "number": pad.number,
                "type": "smd",
                "shape": "roundrect",
                "x": pad.x,
                "y": pad.y,
                "width": pad.width,
                "height": pad.height,
                "layers": ["F.Cu", "F.Paste", "F.Mask"],
                "rotation": pad.rotation,
                "roundrect_rratio": 0.25,
            }
            for pad in spec.pads
        ],
    }


def _symbol_definition_count() -> int:
    if not SYMBOL_LIBRARY.exists():
        return 0
    pattern = re.compile(r'(?m)^  \(symbol "RP2040-Tiny"$')
    return len(pattern.findall(SYMBOL_LIBRARY.read_text()))


def _outline_graphics() -> list[dict[str, object]]:
    return [
        {
            "type": "rect",
            "start": {"x": -9.0, "y": -1.59},
            "end": {"x": 9.0, "y": 21.91},
            "stroke_width_mm": 0.1,
            "fill": "none",
        },
        {
            "type": "rect",
            "start": {"x": -6.0, "y": -1.59},
            "end": {"x": 6.0, "y": 0.66},
            "stroke_width_mm": 0.1,
            "fill": "none",
        },
    ]


def apply_mcu_library(client: McpClient) -> None:
    client.tool_schemas("library")
    MCU_ROOT.mkdir(parents=True, exist_ok=True)
    FOOTPRINT_LIBRARY.mkdir(parents=True, exist_ok=True)
    for _ in range(_symbol_definition_count()):
        client.call_tool(
            "delete_symbol",
            {
                "library_path": str(SYMBOL_LIBRARY),
                "symbol_name": "RP2040-Tiny",
            },
        )
    client.call_tool("create_symbol", symbol_payload())
    client.call_tool("create_footprint", footprint_payload())
    client.call_tool(
        "set_footprint_graphics",
        {
            "footprint_path": str(FOOTPRINT_PATH),
            "selector": {"layer": "F.Fab"},
            "mode": "replace",
            "graphics": _outline_graphics(),
        },
    )
    client.call_tool(
        "set_footprint_graphics",
        {
            "footprint_path": str(FOOTPRINT_PATH),
            "selector": {"layer": "F.CrtYd"},
            "mode": "replace",
            "graphics": [
                {
                    "type": "rect",
                    "start": {"x": -9.5, "y": -2.09},
                    "end": {"x": 9.5, "y": 22.41},
                    "stroke_width_mm": 0.05,
                    "fill": "none",
                }
            ],
        },
    )
    client.call_tool(
        "set_footprint_metadata",
        {
            "footprint_path": str(FOOTPRINT_PATH),
            "description": (
                "Waveshare RP2040-Tiny SMD castellated module, "
                "18x23.5mm body, FPC connector at rear edge"
            ),
            "tags": ["rp2040", "waveshare", "tiny", "castellated", "smd", "fpc"],
            "attributes": ["smd", "exclude_from_pos_files"],
        },
    )
    client.call_tool(
        "set_footprint_models",
        {
            "footprint_path": str(FOOTPRINT_PATH),
            "mode": "replace",
            "models": [
                {
                    "path": "../RP2040-Tiny-V1.1.step",
                    "offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    "rotate": {"x": 0.0, "y": 0.0, "z": 0.0},
                }
            ],
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the audited RP2040-Tiny project library through Konnect."
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
        apply_mcu_library(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
