from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

from tools.lh60_design.core_library import (
    FOOTPRINT_LIBRARY,
    PROJECT,
    core_footprint_specs,
    core_symbol_specs,
)
from tools.lh60_design.mcp import McpClient


ROOT = Path(__file__).resolve().parents[1]
MM_TOL = 1e-6


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, abs_tol=MM_TOL):
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def _connector_symbols():
    return [
        symbol for symbol in core_symbol_specs() if symbol.name.startswith("Conn_01x")
    ]


def _connector_footprints():
    return [
        footprint
        for footprint in core_footprint_specs()
        if footprint.name.startswith("PinHeader_1x")
    ]


def _assert_symbol_contract(client: McpClient) -> None:
    for spec in _connector_symbols():
        data = client.call_tool_json(
            "get_symbol_info",
            {"lib_id": f"lh60-core:{spec.name}", "project_dir": str(ROOT)},
        )
        if data["library"] != "lh60-core":
            raise AssertionError(f"{spec.name}: unexpected library {data['library']}")
        if data["name"] != spec.name:
            raise AssertionError(f"{spec.name}: unexpected live name {data['name']}")
        if data["pin_count"] != len(spec.pins):
            raise AssertionError(f"{spec.name}: unexpected pin_count {data['pin_count']}")
        if data["properties"]["Reference"] != spec.reference_prefix:
            raise AssertionError(
                f"{spec.name}: unexpected Reference {data['properties']['Reference']}"
            )
        if data["properties"]["Value"] != spec.value:
            raise AssertionError(
                f"{spec.name}: unexpected Value {data['properties']['Value']}"
            )

        live_pins = data["pins"]
        if [pin["number"] for pin in live_pins] != [pin.number for pin in spec.pins]:
            raise AssertionError(f"{spec.name}: live pin numbers are not sequential")
        if [pin["name"] for pin in live_pins] != [pin.name for pin in spec.pins]:
            raise AssertionError(f"{spec.name}: live pin names do not match spec")
        if [pin["type"] for pin in live_pins] != [pin.pin_type for pin in spec.pins]:
            raise AssertionError(f"{spec.name}: live pin types do not match spec")

        x_values = [pin["x"] for pin in live_pins]
        if not all(x < 0 for x in x_values):
            raise AssertionError(f"{spec.name}: pins are not on the left side: {x_values}")
        for index in range(1, len(live_pins)):
            _assert_close(
                live_pins[index]["y"] - live_pins[index - 1]["y"],
                2.54,
                f"{spec.name}: pin pitch",
            )

        print(
            f"symbol {spec.name}: {data['pin_count']} pins, ref={data['properties']['Reference']}"
        )


def _graphics_by_layer(graphics: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    by_layer: dict[str, list[dict[str, object]]] = {}
    for graphic in graphics:
        by_layer.setdefault(str(graphic["layer"]), []).append(graphic)
    return by_layer


def _expected_connector_silks(pin_count: int) -> list[dict[str, object]]:
    bottom_y = (pin_count - 1) * 2.54 + 1.27
    return [
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
    ]


def _normalize_connector_silk(silks: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "type": str(item["type"]),
            "start": {
                "x": float(item["start"]["x"]),
                "y": float(item["start"]["y"]),
            },
            "end": {
                "x": float(item["end"]["x"]),
                "y": float(item["end"]["y"]),
            },
            "stroke_width_mm": float(item["stroke_width_mm"]),
        }
        for item in silks
    ]


def _silks_match_expected_geometry(
    silks: list[dict[str, object]],
    expected_silks: list[dict[str, object]],
) -> bool:
    return _normalize_connector_silk(silks) == expected_silks


def _assert_footprint_contract(client: McpClient) -> None:
    for spec in _connector_footprints():
        path = FOOTPRINT_LIBRARY / f"{spec.name}.kicad_mod"
        data = client.call_tool_json(
            "get_footprint_info",
            {"footprint_path": str(path), "include_graphics": True},
        )
        if data["name"] != spec.name:
            raise AssertionError(f"{spec.name}: unexpected live footprint name")
        if data["description"] != spec.description:
            raise AssertionError(f"{spec.name}: description drifted")
        if data["pad_count"] != len(spec.pads):
            raise AssertionError(f"{spec.name}: unexpected pad_count {data['pad_count']}")
        if not data["has_courtyard"]:
            raise AssertionError(f"{spec.name}: courtyard missing")
        if data["has_3d_model"]:
            raise AssertionError(f"{spec.name}: unexpected 3D model")

        graphics = _graphics_by_layer(data["graphics"])
        if set(graphics) != {"F.Fab", "F.CrtYd", "F.SilkS"}:
            raise AssertionError(f"{spec.name}: unexpected graphic layers {sorted(graphics)}")
        if data["graphic_count"] != 8:
            raise AssertionError(f"{spec.name}: unexpected graphic_count {data['graphic_count']}")

        bottom_y = (len(spec.pads) - 1) * 2.54 + 1.27
        fab = graphics["F.Fab"]
        if len(fab) != 1 or fab[0]["type"] != "rect":
            raise AssertionError(f"{spec.name}: unexpected F.Fab graphics {fab}")
        _assert_close(fab[0]["start"]["x"], -1.27, f"{spec.name}: fab start x")
        _assert_close(fab[0]["start"]["y"], -1.27, f"{spec.name}: fab start y")
        _assert_close(fab[0]["end"]["x"], 1.27, f"{spec.name}: fab end x")
        _assert_close(fab[0]["end"]["y"], bottom_y, f"{spec.name}: fab end y")
        _assert_close(fab[0]["stroke_width_mm"], 0.1, f"{spec.name}: fab stroke")

        courtyard = graphics["F.CrtYd"]
        if len(courtyard) != 1 or courtyard[0]["type"] != "rect":
            raise AssertionError(f"{spec.name}: unexpected F.CrtYd graphics {courtyard}")
        _assert_close(courtyard[0]["start"]["x"], -1.77, f"{spec.name}: crtyd start x")
        _assert_close(courtyard[0]["start"]["y"], -1.77, f"{spec.name}: crtyd start y")
        _assert_close(courtyard[0]["end"]["x"], 1.77, f"{spec.name}: crtyd end x")
        _assert_close(courtyard[0]["end"]["y"], bottom_y + 0.5, f"{spec.name}: crtyd end y")
        _assert_close(
            courtyard[0]["stroke_width_mm"], 0.05, f"{spec.name}: crtyd stroke"
        )

        silks = graphics["F.SilkS"]
        if len(silks) != 6:
            raise AssertionError(f"{spec.name}: unexpected F.SilkS primitive count {len(silks)}")
        for item in silks:
            if item.get("layer") != "F.SilkS":
                raise AssertionError(f"{spec.name}: unexpected silk layer {item.get('layer')}")
            if item["type"] != "line":
                raise AssertionError(f"{spec.name}: non-line silkscreen primitive {item}")
            _assert_close(item["stroke_width_mm"], 0.15, f"{spec.name}: silk stroke")
        expected_silks = _expected_connector_silks(len(spec.pads))
        if not _silks_match_expected_geometry(silks, expected_silks):
            raise AssertionError(
                f"{spec.name}: silk coordinates drifted: {_normalize_connector_silk(silks)}"
            )

        print(f"footprint {spec.name}: pads={data['pad_count']} graphics={data['graphic_count']}")


def _assert_project_registration(client: McpClient) -> None:
    symbol_libraries = client.call_tool_json(
        "list_symbol_libraries",
        {"project": str(PROJECT)},
    )["libraries"]
    footprint_libraries = client.call_tool_json(
        "list_footprint_libraries",
        {"project": str(PROJECT)},
    )["libraries"]

    symbol_entry = next(
        library for library in symbol_libraries if library["nickname"] == "lh60-core"
    )
    footprint_entry = next(
        library for library in footprint_libraries if library["nickname"] == "lh60-core"
    )
    if symbol_entry["scope"] != "project":
        raise AssertionError(f"symbol library scope drifted: {symbol_entry['scope']}")
    if footprint_entry["scope"] != "project":
        raise AssertionError(f"footprint library scope drifted: {footprint_entry['scope']}")
    if symbol_entry["uri"] != "${KIPRJMOD}/lib/lh60-core/lh60-core.kicad_sym":
        raise AssertionError(f"symbol library uri drifted: {symbol_entry['uri']}")
    if footprint_entry["uri"] != "${KIPRJMOD}/lib/lh60-core/lh60-core.pretty":
        raise AssertionError(f"footprint library uri drifted: {footprint_entry['uri']}")

    print("registration lh60-core: project-scoped portable URIs confirmed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live acceptance checks for the LH60 connector symbol/footprint library."
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with McpClient(args.konnect, args.config) as client:
        client.tool_schemas("library")
        _assert_symbol_contract(client)
        _assert_footprint_contract(client)
        _assert_project_registration(client)
    print("connector library live acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
