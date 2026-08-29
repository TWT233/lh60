from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys

from tools.lh60_design.interconnect import DATASHEET_URL, PIN_COUNT, interboard_contract
from tools.lh60_design.mcp import McpClient


ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = ROOT / "lib" / "lh60-interconnect"
SYMBOL_LIBRARY = LIBRARY_ROOT / "lh60-interconnect.kicad_sym"
FOOTPRINT_LIBRARY = LIBRARY_ROOT / "lh60-interconnect.pretty"
FOOTPRINT_PATH = FOOTPRINT_LIBRARY / "FPC-05F-24PH20.kicad_mod"
PROJECT = ROOT / "lh60.kicad_pro"
BOARD = ROOT / "lh60.kicad_pcb"

NICKNAME = "lh60-interconnect"
SYMBOL_NAME = "FPC-05F-24PH20"
FOOTPRINT_LIB_ID = f"{NICKNAME}:{SYMBOL_NAME}"
CUSTOM_CLEARANCE_RULE_NAME = "lh60-interconnect:C2856805-general-clearance"
CUSTOM_CLEARANCE_RULE_CONDITION = (
    "!(A.Type == 'Pad' && B.Type == 'Pad' && "
    "A.memberOfFootprint('FPC-05F-24PH20') && "
    "B.memberOfFootprint('FPC-05F-24PH20') && "
    "A.Reference == B.Reference)"
)
COPPER_LAYERS = ("F.Cu", "B.Cu")


@dataclass(frozen=True)
class InterconnectSymbolPinSpec:
    number: str
    name: str
    pin_type: str
    x: float
    y: float
    angle: float


@dataclass(frozen=True)
class InterconnectSymbolSpec:
    name: str
    reference_prefix: str
    value: str
    footprint: str
    manufacturer: str
    mpn: str
    lcsc_part: str
    datasheet_url: str
    pins: tuple[InterconnectSymbolPinSpec, ...]


@dataclass(frozen=True)
class InterconnectPadSpec:
    number: str
    x: float
    y: float
    width: float
    height: float
    layers: tuple[str, ...]
    pad_type: str = "smd"
    shape: str = "roundrect"
    roundrect_rratio: float = 0.25


@dataclass(frozen=True)
class InterconnectFootprintSpec:
    name: str
    description: str
    manufacturer: str
    mpn: str
    lcsc_part: str
    datasheet_url: str
    pads: tuple[InterconnectPadSpec, ...]
    body_width_mm: float
    body_depth_mm: float
    body_height_mm: float
    fab_min_x: float
    fab_max_x: float
    fab_min_y: float
    fab_max_y: float
    courtyard_clearance_mm: float
    mouth_direction: str
    pin1_top_view: str
    tags: tuple[str, ...]
    attributes: tuple[str, ...]
    step_model: str | None = None


def interconnect_symbol_spec() -> InterconnectSymbolSpec:
    contract = interboard_contract()
    return InterconnectSymbolSpec(
        name=contract.connector.mpn,
        reference_prefix="J",
        value=contract.connector.mpn,
        footprint=FOOTPRINT_LIB_ID,
        manufacturer=contract.connector.manufacturer,
        mpn=contract.connector.mpn,
        lcsc_part=contract.connector.lcsc_part,
        datasheet_url=contract.connector.datasheet_url,
        pins=tuple(
            InterconnectSymbolPinSpec(
                number=str(index),
                name=str(index),
                pin_type="passive",
                x=-5.08,
                y=(index - 1) * 2.54,
                angle=0.0,
            )
            for index in range(1, PIN_COUNT + 1)
        ),
    )


def interconnect_footprint_spec() -> InterconnectFootprintSpec:
    signal_pads = tuple(
        InterconnectPadSpec(
            number=str(index + 1),
            x=-5.75 + index * 0.50,
            y=0.0,
            width=0.30,
            height=1.25,
            layers=("F.Cu", "F.Paste", "F.Mask"),
        )
        for index in range(PIN_COUNT)
    )
    hold_downs = (
        InterconnectPadSpec(
            number="",
            x=-7.44,
            y=2.575,
            width=2.00,
            height=2.50,
            layers=("F.Cu", "F.Paste", "F.Mask"),
            shape="rect",
            roundrect_rratio=0.0,
        ),
        InterconnectPadSpec(
            number="",
            x=7.44,
            y=2.575,
            width=2.00,
            height=2.50,
            layers=("F.Cu", "F.Paste", "F.Mask"),
            shape="rect",
            roundrect_rratio=0.0,
        ),
    )
    contract = interboard_contract()
    return InterconnectFootprintSpec(
        name=contract.connector.mpn,
        description=(
            "XUNPU FPC-05F-24PH20 24-pin 0.50 mm pitch horizontal SMT "
            "bottom-contact front-flip FFC connector, LCSC C2856805"
        ),
        manufacturer=contract.connector.manufacturer,
        mpn=contract.connector.mpn,
        lcsc_part=contract.connector.lcsc_part,
        datasheet_url=contract.connector.datasheet_url,
        pads=signal_pads + hold_downs,
        body_width_mm=16.40,
        body_depth_mm=5.12,
        body_height_mm=2.00,
        fab_min_x=-8.20,
        fab_max_x=8.20,
        fab_min_y=0.68,
        fab_max_y=5.80,
        courtyard_clearance_mm=0.25,
        mouth_direction="+Y",
        pin1_top_view="leftmost signal pad",
        tags=("lh60", "ffc", "fpc", "xunpu", "c2856805"),
        attributes=("smd",),
    )


def interconnect_symbol_payload() -> dict[str, object]:
    spec = interconnect_symbol_spec()
    return {
        "library_path": str(SYMBOL_LIBRARY),
        "name": spec.name,
        "reference_prefix": spec.reference_prefix,
        "value": spec.value,
        "datasheet": spec.datasheet_url,
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


def interconnect_footprint_payload() -> dict[str, object]:
    spec = interconnect_footprint_spec()
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
        if pad.shape == "roundrect":
            payload["roundrect_rratio"] = pad.roundrect_rratio
        pads.append(payload)
    return {
        "output": str(FOOTPRINT_PATH),
        "name": spec.name,
        "description": spec.description,
        "body_width": spec.body_width_mm,
        "body_height": spec.body_depth_mm,
        "courtyard_clearance": spec.courtyard_clearance_mm,
        "pads": pads,
    }


def interconnect_graphics_by_layer() -> dict[str, list[dict[str, object]]]:
    return {
        "F.Fab": [
            {
                "type": "rect",
                "start": {"x": -8.20, "y": 0.68},
                "end": {"x": 8.20, "y": 5.80},
                "stroke_width_mm": 0.1,
                "fill": "none",
            },
            {
                "type": "line",
                "start": {"x": -6.25, "y": 0.68},
                "end": {"x": 6.25, "y": 0.68},
                "stroke_width_mm": 0.1,
            },
            {
                "type": "line",
                "start": {"x": -6.25, "y": 5.80},
                "end": {"x": 6.25, "y": 5.80},
                "stroke_width_mm": 0.1,
            },
        ],
        "F.CrtYd": [
            {
                "type": "rect",
                "start": {"x": -8.69, "y": -0.875},
                "end": {"x": 8.69, "y": 6.05},
                "stroke_width_mm": 0.05,
                "fill": "none",
            }
        ],
        "F.SilkS": [
            {
                "type": "line",
                "start": {"x": -8.20, "y": 0.45},
                "end": {"x": -8.20, "y": 5.95},
                "stroke_width_mm": 0.12,
            },
            {
                "type": "line",
                "start": {"x": 8.20, "y": 0.45},
                "end": {"x": 8.20, "y": 5.95},
                "stroke_width_mm": 0.12,
            },
            {
                "type": "line",
                "start": {"x": -7.0, "y": 6.15},
                "end": {"x": 7.0, "y": 6.15},
                "stroke_width_mm": 0.12,
            },
            {
                "type": "circle",
                "center": {"x": -6.45, "y": -0.95},
                "radius_mm": 0.20,
                "stroke_width_mm": 0.1,
                "fill": "solid",
            },
        ],
    }


def _symbol_definition_count() -> int:
    if not SYMBOL_LIBRARY.exists():
        return 0
    pattern = re.compile(rf'(?m)^  \(symbol "{re.escape(SYMBOL_NAME)}"$')
    return len(pattern.findall(SYMBOL_LIBRARY.read_text()))


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


def _assert_effective_clearance_stack(custom_rules: list[dict[str, object]]) -> None:
    layer_clearance_rules = [
        rule
        for rule in custom_rules
        if rule.get("constraint") == "clearance" and rule.get("layer") in set(COPPER_LAYERS)
    ]
    for rule in layer_clearance_rules:
        if not str(rule.get("condition") or "") and float(rule["minimum_mm"]) > 0.20:
            raise RuntimeError(
                "conflicting unconditional layer clearance rule defeats C2856805 exception: "
                f"{rule}"
            )

    floor_layers = {
        str(rule["layer"])
        for rule in layer_clearance_rules
        if float(rule["minimum_mm"]) == 0.20 and not str(rule.get("condition") or "")
    }
    if floor_layers != set(COPPER_LAYERS):
        raise RuntimeError(f"missing 0.20 mm layer floor rules: {layer_clearance_rules}")


def apply_interconnect_library(client: McpClient) -> None:
    client.tool_schemas("library")
    client.tool_schemas("verification")
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    FOOTPRINT_LIBRARY.mkdir(parents=True, exist_ok=True)

    for _ in range(_symbol_definition_count()):
        client.call_tool(
            "delete_symbol",
            {
                "library_path": str(SYMBOL_LIBRARY),
                "symbol_name": SYMBOL_NAME,
            },
        )
    client.call_tool("create_symbol", interconnect_symbol_payload())
    client.call_tool("create_footprint", interconnect_footprint_payload())
    for layer, graphics in interconnect_graphics_by_layer().items():
        _replace_graphics(client, FOOTPRINT_PATH, layer, graphics)
    footprint_spec = interconnect_footprint_spec()
    client.call_tool(
        "set_footprint_metadata",
        {
            "footprint_path": str(FOOTPRINT_PATH),
            "description": footprint_spec.description,
            "tags": list(footprint_spec.tags),
            "attributes": list(footprint_spec.attributes),
        },
    )
    client.call_tool(
        "set_footprint_models",
        {
            "footprint_path": str(FOOTPRINT_PATH),
            "mode": "delete",
        },
    )
    client.call_tool(
        "register_symbol_library",
        {
            "library_path": str(SYMBOL_LIBRARY),
            "nickname": NICKNAME,
            "project": str(PROJECT),
            "scope": "project",
            "replace_existing": True,
        },
    )
    client.call_tool(
        "register_footprint_library",
        {
            "library_path": str(FOOTPRINT_LIBRARY),
            "nickname": NICKNAME,
            "project": str(PROJECT),
            "scope": "project",
            "replace_existing": True,
        },
    )
    client.call_tool(
        "set_design_rules",
        {
            "board": str(BOARD),
            "min_clearance": 0.20,
            "min_trace_width": 0.25,
            "min_via_drill": 0.30,
            "min_via_size": 0.70,
            "min_hole_to_hole": 0.45,
        },
    )
    rules = client.call_tool_json("get_design_rules", {"board": str(BOARD)})["rules"]
    expected_rules = {
        "min_clearance": 0.20,
        "min_trace_width": 0.25,
        "min_via_drill": 0.30,
        "min_via_size": 0.70,
    }
    for key, expected in expected_rules.items():
        if rules.get(key) != expected:
            raise RuntimeError(f"design rule {key} readback mismatch: {rules.get(key)}")
    for layer in COPPER_LAYERS:
        client.call_tool(
            "set_layer_constraints",
            {
                "board": str(BOARD),
                "layer": layer,
                "min_clearance": 0.20,
                "min_trace_width": 0.25,
            },
        )
    client.call_tool(
        "set_custom_rule",
        {
            "board": str(BOARD),
            "name": CUSTOM_CLEARANCE_RULE_NAME,
            "constraint": "clearance",
            "minimum_mm": 0.25,
            "condition": CUSTOM_CLEARANCE_RULE_CONDITION,
        },
    )
    custom_rules = client.call_tool_json("list_custom_rules", {"board": str(BOARD)})["rules"]
    expected_custom_rule = {
        "name": CUSTOM_CLEARANCE_RULE_NAME,
        "constraint": "clearance",
        "minimum_mm": 0.25,
        "condition": CUSTOM_CLEARANCE_RULE_CONDITION,
        "layer": None,
    }
    if expected_custom_rule not in custom_rules:
        raise RuntimeError("custom clearance rule readback mismatch")
    _assert_effective_clearance_stack(custom_rules)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the audited C2856805 interconnect library through Konnect."
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
        apply_interconnect_library(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
