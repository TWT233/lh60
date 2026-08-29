from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lh60_design.interconnect_library import (
    BOARD,
    CUSTOM_CLEARANCE_RULE_CONDITION,
    CUSTOM_CLEARANCE_RULE_NAME,
    FOOTPRINT_LIBRARY,
    FOOTPRINT_PATH,
    NICKNAME,
    PROJECT,
    SYMBOL_NAME,
    interconnect_footprint_spec,
    interconnect_graphics_by_layer,
    interconnect_symbol_spec,
)
from tools.lh60_design.mcp import McpClient


MM_TOL = 1e-6


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, abs_tol=MM_TOL):
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def _graphics_by_layer(graphics: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    by_layer: dict[str, list[dict[str, object]]] = {}
    for graphic in graphics:
        by_layer.setdefault(str(graphic["layer"]), []).append(graphic)
    return by_layer


def _normalize_graphic(item: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {"type": str(item["type"])}
    if "start" in item:
        result["start"] = {
            "x": float(item["start"]["x"]),
            "y": float(item["start"]["y"]),
        }
    if "end" in item:
        result["end"] = {
            "x": float(item["end"]["x"]),
            "y": float(item["end"]["y"]),
        }
    if "center" in item:
        result["center"] = {
            "x": float(item["center"]["x"]),
            "y": float(item["center"]["y"]),
        }
    if "radius_mm" in item:
        result["radius_mm"] = float(item["radius_mm"])
    if "stroke_width_mm" in item:
        result["stroke_width_mm"] = float(item["stroke_width_mm"])
    if "fill" in item:
        result["fill"] = str(item["fill"])
    return result


def _assert_graphics_equal(
    actual_items: list[dict[str, object]],
    expected_items: list[dict[str, object]],
    label: str,
) -> None:
    if len(actual_items) != len(expected_items):
        raise AssertionError(f"{label} graphic count drifted: {actual_items}")
    for index, (actual, expected) in enumerate(zip(actual_items, expected_items)):
        if set(actual) != set(expected):
            raise AssertionError(f"{label}[{index}] keys drifted: {actual}")
        for key, expected_value in expected.items():
            actual_value = actual[key]
            if isinstance(expected_value, float):
                _assert_close(float(actual_value), expected_value, f"{label}[{index}].{key}")
            elif isinstance(expected_value, dict):
                for axis, axis_expected in expected_value.items():
                    _assert_close(
                        float(actual_value[axis]),
                        float(axis_expected),
                        f"{label}[{index}].{key}.{axis}",
                    )
            elif actual_value != expected_value:
                raise AssertionError(
                    f"{label}[{index}].{key}: expected {expected_value}, got {actual_value}"
                )


def _parse_balanced_forms(text: str, atom: str) -> list[str]:
    forms: list[str] = []
    token = f"({atom} "
    start = 0
    while True:
        index = text.find(token, start)
        if index == -1:
            return forms
        depth = 0
        in_string = False
        escaped = False
        for pos in range(index, len(text)):
            char = text[pos]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    forms.append(text[index : pos + 1])
                    start = pos + 1
                    break
        else:
            raise AssertionError(f"unterminated ({atom}) form")


def _extract_quoted(form: str) -> list[str]:
    return re.findall(r'"((?:[^"\\]|\\.)*)"', form)


def _parse_footprint_pads(text: str) -> list[dict[str, object]]:
    pads: list[dict[str, object]] = []
    for form in _parse_balanced_forms(text, "pad"):
        match = re.match(r'\(pad\s+"((?:[^"\\]|\\.)*)"\s+(\S+)\s+(\S+)', form)
        if not match:
            raise AssertionError(f"cannot parse pad header: {form}")
        at = re.search(r"\(at\s+([-0-9.]+)\s+([-0-9.]+)(?:\s+[-0-9.]+)?\)", form)
        size = re.search(r"\(size\s+([-0-9.]+)\s+([-0-9.]+)\)", form)
        layers = re.search(r"\(layers\s+([^)]*)\)", form)
        if at is None or size is None or layers is None:
            raise AssertionError(f"missing pad geometry fields: {form}")
        pads.append(
            {
                "number": match.group(1),
                "type": match.group(2),
                "shape": match.group(3),
                "x": float(at.group(1)),
                "y": float(at.group(2)),
                "width": float(size.group(1)),
                "height": float(size.group(2)),
                "layers": tuple(_extract_quoted(layers.group(0))),
            }
        )
    return pads


def _assert_symbol_contract(client: McpClient) -> None:
    spec = interconnect_symbol_spec()
    data = client.call_tool_json(
        "get_symbol_info",
        {"lib_id": f"{NICKNAME}:{SYMBOL_NAME}", "project_dir": str(ROOT)},
    )
    if data["library"] != NICKNAME:
        raise AssertionError(f"unexpected symbol library: {data['library']}")
    if data["name"] != spec.name:
        raise AssertionError(f"unexpected symbol name: {data['name']}")
    if data["pin_count"] != 24:
        raise AssertionError(f"unexpected symbol pin count: {data['pin_count']}")
    if data["properties"]["Reference"] != spec.reference_prefix:
        raise AssertionError("symbol Reference property drifted")
    if data["properties"]["Value"] != spec.value:
        raise AssertionError("symbol Value property drifted")
    if data["properties"]["Datasheet"] != spec.datasheet_url:
        raise AssertionError("symbol Datasheet property drifted")
    live_pins = data["pins"]
    expected = [(pin.number, pin.name, pin.pin_type) for pin in spec.pins]
    actual = [(pin["number"], pin["name"], pin["type"]) for pin in live_pins]
    if actual != expected:
        raise AssertionError(f"symbol pins drifted: {actual}")
    print("symbol FPC-05F-24PH20: 24 passive sequential pins confirmed")


def _assert_footprint_pads_from_written_library() -> None:
    spec = interconnect_footprint_spec()
    pads = _parse_footprint_pads(FOOTPRINT_PATH.read_text())
    expected = [
        {
            "number": pad.number,
            "type": pad.pad_type,
            "shape": pad.shape,
            "x": pad.x,
            "y": pad.y,
            "width": pad.width,
            "height": pad.height,
            "layers": pad.layers,
        }
        for pad in spec.pads
    ]
    if pads != expected:
        raise AssertionError(f"footprint pad geometry drifted: {pads}")
    signal = [pad for pad in pads if pad["number"]]
    hold_downs = [pad for pad in pads if not pad["number"]]
    if len(signal) != 24 or len(hold_downs) != 2:
        raise AssertionError(f"unexpected signal/hold-down split: {len(signal)}/{len(hold_downs)}")
    if any(pad["number"] in {"25", "26"} for pad in pads):
        raise AssertionError("mechanical hold-downs must not be numbered 25/26")
    print("footprint pads: 24 electrical + 2 unnumbered mechanical lands confirmed")


def _assert_footprint_info_contract(client: McpClient) -> None:
    spec = interconnect_footprint_spec()
    data = client.call_tool_json(
        "get_footprint_info",
        {"footprint_path": str(FOOTPRINT_PATH), "include_graphics": True},
    )
    if data["name"] != spec.name:
        raise AssertionError(f"unexpected footprint name: {data['name']}")
    if data["description"] != spec.description:
        raise AssertionError("footprint description drifted")
    if data["pad_count"] != len(spec.pads):
        raise AssertionError(f"unexpected pad count: {data['pad_count']}")
    if data["has_3d_model"]:
        raise AssertionError("approximate STEP model must not be associated")
    if not data["has_courtyard"]:
        raise AssertionError("courtyard missing")

    live = _graphics_by_layer(data["graphics"])
    expected = interconnect_graphics_by_layer()
    if set(live) != set(expected):
        raise AssertionError(f"unexpected graphic layers: {sorted(live)}")
    for layer, expected_items in expected.items():
        actual_items = [_normalize_graphic(item) for item in live[layer]]
        _assert_graphics_equal(actual_items, expected_items, layer)
    print(f"footprint graphics: {data['graphic_count']} primitives confirmed")


def _assert_project_registration(client: McpClient) -> None:
    symbol_libraries = client.call_tool_json(
        "list_symbol_libraries",
        {"project": str(PROJECT)},
    )["libraries"]
    footprint_libraries = client.call_tool_json(
        "list_footprint_libraries",
        {"project": str(PROJECT)},
    )["libraries"]

    symbol_entry = next(library for library in symbol_libraries if library["nickname"] == NICKNAME)
    footprint_entry = next(
        library for library in footprint_libraries if library["nickname"] == NICKNAME
    )
    if symbol_entry["scope"] != "project":
        raise AssertionError(f"symbol library scope drifted: {symbol_entry['scope']}")
    if footprint_entry["scope"] != "project":
        raise AssertionError(f"footprint library scope drifted: {footprint_entry['scope']}")
    if symbol_entry["uri"] != "${KIPRJMOD}/lib/lh60-interconnect/lh60-interconnect.kicad_sym":
        raise AssertionError(f"symbol library uri drifted: {symbol_entry['uri']}")
    if footprint_entry["uri"] != "${KIPRJMOD}/lib/lh60-interconnect/lh60-interconnect.pretty":
        raise AssertionError(f"footprint library uri drifted: {footprint_entry['uri']}")
    print("registration lh60-interconnect: project-scoped portable URIs confirmed")


def _assert_design_rules(client: McpClient) -> None:
    rules = client.call_tool_json("get_design_rules", {"board": str(BOARD)})["rules"]
    expected = {
        "min_clearance": 0.20,
        "min_trace_width": 0.25,
        "min_via_drill": 0.30,
        "min_via_size": 0.70,
    }
    for key, value in expected.items():
        if rules.get(key) != value:
            raise AssertionError(f"design rule {key} drifted: {rules.get(key)}")
    custom_rules = client.call_tool_json("list_custom_rules", {"board": str(BOARD)})["rules"]
    expected_custom_rule = {
        "name": CUSTOM_CLEARANCE_RULE_NAME,
        "constraint": "clearance",
        "minimum_mm": 0.25,
        "condition": CUSTOM_CLEARANCE_RULE_CONDITION,
        "layer": None,
    }
    if expected_custom_rule not in custom_rules:
        raise AssertionError(f"custom clearance rule missing: {custom_rules}")
    print("root board clearance rules: 0.20 mm floor plus 0.25 mm exception rule confirmed")


def _run_footprint_svg_export(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "kicad-cli",
        "fp",
        "export",
        "svg",
        "--output",
        str(output_dir),
        str(FOOTPRINT_LIBRARY),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    output = output_dir / f"{SYMBOL_NAME}.svg"
    if not output.is_file() or output.stat().st_size == 0:
        raise AssertionError(f"footprint SVG export missing or empty: {output}")
    print(f"footprint SVG export: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live acceptance checks for the LH60 C2856805 interconnect library."
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
        "--svg-output",
        type=Path,
        default=ROOT / "docs" / "reports" / "mcu-tail-ffc-u3-footprint-svg",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with McpClient(args.konnect, args.config) as client:
        client.tool_schemas("library")
        client.tool_schemas("verification")
        _assert_symbol_contract(client)
        _assert_footprint_info_contract(client)
        _assert_project_registration(client)
        _assert_design_rules(client)
    _assert_footprint_pads_from_written_library()
    _run_footprint_svg_export(args.svg_output)
    print("interconnect library live acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
