from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

from shapely import affinity
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

from tools.lh60_design.mcp import McpClient
from tools.lh60_design.socket_geometry import (
    FootprintSpec,
    ModelSpec,
    PadSpec,
    build_footprint_specs,
    choc_v1_pads_rotated_180,
    choc_v1_v2_pads,
    gateron_pads,
)


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "lib" / "lh60-sockets"

REQUIRED_TOOL_FIELDS = {
    "create_footprint": {
        "output",
        "name",
        "pads",
        "layers",
        "rotation",
        "roundrect_rratio",
    },
    "set_footprint_graphics": {
        "footprint_path",
        "selector",
        "mode",
        "graphics",
    },
    "set_footprint_metadata": {
        "footprint_path",
        "description",
        "tags",
        "attributes",
    },
    "set_footprint_models": {
        "footprint_path",
        "mode",
        "models",
    },
}


def _circle_from_three_points(
    start: tuple[float, float],
    middle: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], float]:
    start_x, start_y = start
    middle_x, middle_y = middle
    end_x, end_y = end
    determinant = 2 * (
        start_x * (middle_y - end_y)
        + middle_x * (end_y - start_y)
        + end_x * (start_y - middle_y)
    )
    if abs(determinant) < 1e-12:
        raise ValueError("arc points are collinear")
    center_x = (
        (start_x**2 + start_y**2) * (middle_y - end_y)
        + (middle_x**2 + middle_y**2) * (end_y - start_y)
        + (end_x**2 + end_y**2) * (start_y - middle_y)
    ) / determinant
    center_y = (
        (start_x**2 + start_y**2) * (end_x - middle_x)
        + (middle_x**2 + middle_y**2) * (start_x - end_x)
        + (end_x**2 + end_y**2) * (middle_x - start_x)
    ) / determinant
    radius = math.hypot(start_x - center_x, start_y - center_y)
    return (center_x, center_y), radius


def _sample_arc(
    start: tuple[float, float],
    middle: tuple[float, float],
    end: tuple[float, float],
    segments: int = 16,
) -> list[tuple[float, float]]:
    center, radius = _circle_from_three_points(start, middle, end)
    center_x, center_y = center
    start_angle = math.atan2(start[1] - center_y, start[0] - center_x)
    middle_angle = math.atan2(middle[1] - center_y, middle[0] - center_x)
    end_angle = math.atan2(end[1] - center_y, end[0] - center_x)
    counter_clockwise_sweep = (end_angle - start_angle) % (2 * math.pi)
    middle_sweep = (middle_angle - start_angle) % (2 * math.pi)
    sweep = (
        counter_clockwise_sweep
        if middle_sweep <= counter_clockwise_sweep
        else -((start_angle - end_angle) % (2 * math.pi))
    )
    return [
        (
            center_x + radius * math.cos(start_angle + sweep * index / segments),
            center_y + radius * math.sin(start_angle + sweep * index / segments),
        )
        for index in range(segments + 1)
    ]


def _extend_arc(
    points: list[tuple[float, float]],
    middle: tuple[float, float],
    end: tuple[float, float],
) -> None:
    points.extend(_sample_arc(points[-1], middle, end)[1:])


def gateron_physical_geometry() -> Polygon:
    body = Polygon(
        [
            (-6.815, 2.525),
            (-2.595, 2.525),
            (-0.395, 3.575),
            (5.025, 3.575),
            (5.025, 7.925),
            (0.405, 7.925),
            (0.405, 7.7),
            (-0.395, 7.7),
            (-0.395, 7.925),
            (-2.595, 6.875),
            (-6.815, 6.875),
        ]
    )
    return unary_union(
        [
            body,
            box(-8.445, 3.615, -6.815, 5.785),
            box(5.025, 4.665, 6.655, 6.835),
        ]
    )


def choc_physical_geometry() -> Polygon:
    points = [(-7.275, 1.825)]
    _extend_arc(points, (-7.165165, 1.559835), (-6.9, 1.45))
    points.append((-3.425, 1.45))
    _extend_arc(points, (-3.159835, 1.559835), (-3.05, 1.825))
    _extend_arc(points, (-2.544759, 3.044759), (-1.325, 3.55))
    points.extend(
        [
            (1.775, 3.55),
            (2.275, 4.05),
            (2.275, 7.75),
            (1.775, 8.25),
            (-2.475, 8.25),
            (-2.975, 7.75),
        ]
    )
    _extend_arc(points, (-3.45256, 6.609686), (-4.600195, 6.15))
    points.append((-6.9, 6.15))
    _extend_arc(points, (-7.165165, 6.040165), (-7.275, 5.775))
    return unary_union(
        [
            Polygon(points),
            box(-9.075, 2.96, -7.275, 4.64),
            box(2.275, 5.06, 4.075, 6.74),
        ]
    )


def _polygons(geometry: Any) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        return [
            polygon
            for item in geometry.geoms
            for polygon in _polygons(item)
            if not polygon.is_empty
        ]
    raise TypeError(f"unsupported geometry: {geometry.geom_type}")


def _pad_geometry(pad: PadSpec) -> Polygon:
    if pad.shape == "circle":
        return Point(pad.x, pad.y).buffer(pad.width / 2, quad_segs=16)
    geometry = box(
        pad.x - pad.width / 2,
        pad.y - pad.height / 2,
        pad.x + pad.width / 2,
        pad.y + pad.height / 2,
    )
    if pad.rotation:
        geometry = affinity.rotate(geometry, -pad.rotation, origin=(pad.x, pad.y))
    return geometry


def _land_pattern(pads: Iterable[PadSpec]) -> Polygon:
    return unary_union([_pad_geometry(pad) for pad in pads])


def _rounded(value: float) -> float:
    rounded = round(value, 3)
    return 0.0 if rounded == -0.0 else rounded


def _polygon_graphics(
    geometry: Any,
    *,
    stroke_width_mm: float,
) -> list[dict[str, Any]]:
    return [
        {
            "type": "poly",
            "points": [
                {"x": _rounded(x), "y": _rounded(y)}
                for x, y in polygon.exterior.coords[:-1]
            ],
            "stroke_width_mm": stroke_width_mm,
            "fill": "none",
        }
        for polygon in _polygons(geometry)
    ]


def _mark_graphics(
    letter: str,
    origin_x: float,
    origin_y: float,
) -> list[dict[str, Any]]:
    line_sets = {
        "G": [
            ((0.8, 0.0), (0.0, 0.0)),
            ((0.0, 0.0), (0.0, 1.4)),
            ((0.0, 1.4), (0.8, 1.4)),
            ((0.8, 1.4), (0.8, 0.8)),
            ((0.8, 0.8), (0.45, 0.8)),
        ],
        "K": [
            ((0.0, 0.0), (0.0, 1.4)),
            ((0.0, 0.7), (0.8, 0.0)),
            ((0.0, 0.7), (0.8, 1.4)),
        ],
        "C": [
            ((0.8, 0.0), (0.0, 0.0)),
            ((0.0, 0.0), (0.0, 1.4)),
            ((0.0, 1.4), (0.8, 1.4)),
        ],
    }
    return [
        {
            "type": "line",
            "start": {
                "x": _rounded(origin_x + start[0]),
                "y": _rounded(origin_y + start[1]),
            },
            "end": {
                "x": _rounded(origin_x + end[0]),
                "y": _rounded(origin_y + end[1]),
            },
            "stroke_width_mm": 0.1,
        }
        for start, end in line_sets[letter]
    ]


def _keycap_graphic(spec: FootprintSpec) -> dict[str, Any]:
    return {
        "type": "rect",
        "start": {"x": _rounded(-spec.keycap_width_mm / 2), "y": -9.525},
        "end": {"x": _rounded(spec.keycap_width_mm / 2), "y": 9.525},
        "stroke_width_mm": 0.12,
        "fill": "none",
    }


def _body_graphics(spec: FootprintSpec) -> list[dict[str, Any]]:
    gateron = gateron_physical_geometry()
    choc = choc_physical_geometry()
    if spec.series == "Gateron-LP":
        return [
            *_polygon_graphics(gateron, stroke_width_mm=0.1),
            *_mark_graphics("G", -1.0, 4.2),
        ]
    if spec.series == "Kailh-Choc-V1V2":
        return [
            *_polygon_graphics(choc, stroke_width_mm=0.1),
            *_mark_graphics("K", -0.4, 4.3),
        ]
    rotated_choc = affinity.rotate(choc, 180, origin=(0, 0))
    return [
        *_polygon_graphics(gateron, stroke_width_mm=0.1),
        *_mark_graphics("G", -1.0, 4.2),
        *_polygon_graphics(rotated_choc, stroke_width_mm=0.1),
        *_mark_graphics("C", -0.4, -7.0),
    ]


def _courtyard_graphics(spec: FootprintSpec) -> list[dict[str, Any]]:
    gateron = unary_union(
        [gateron_physical_geometry(), _land_pattern(gateron_pads())]
    ).buffer(spec.courtyard_clearance_mm, quad_segs=8, join_style="round")
    choc = unary_union(
        [choc_physical_geometry(), _land_pattern(choc_v1_v2_pads())]
    ).buffer(spec.courtyard_clearance_mm, quad_segs=8, join_style="round")
    if spec.series == "Gateron-LP":
        geometries = [gateron]
    elif spec.series == "Kailh-Choc-V1V2":
        geometries = [choc]
    else:
        rotated_choc_body = affinity.rotate(
            choc_physical_geometry(), 180, origin=(0, 0)
        )
        rotated_choc = unary_union(
            [rotated_choc_body, _land_pattern(choc_v1_pads_rotated_180())]
        ).buffer(spec.courtyard_clearance_mm, quad_segs=8, join_style="round")
        merged = unary_union([gateron, rotated_choc])
        geometries = [
            Polygon(polygon.exterior)
            for polygon in _polygons(merged)
        ]
    return [
        graphic
        for geometry in geometries
        for graphic in _polygon_graphics(geometry, stroke_width_mm=0.05)
    ]


def _pad_payload(pad: PadSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "number": pad.number,
        "type": pad.pad_type,
        "shape": pad.shape,
        "x": pad.x,
        "y": pad.y,
        "width": pad.width,
        "height": pad.height,
        "layers": list(pad.layers),
    }
    if pad.drill is not None:
        payload["drill"] = pad.drill
    if pad.rotation:
        payload["rotation"] = pad.rotation
    if pad.roundrect_rratio is not None:
        payload["roundrect_rratio"] = pad.roundrect_rratio
    return payload


def _model_payload(model: ModelSpec) -> dict[str, Any]:
    return {
        "path": model.path,
        "offset": dict(zip(("x", "y", "z"), model.offset, strict=True)),
        "scale": dict(zip(("x", "y", "z"), model.scale, strict=True)),
        "rotate": dict(zip(("x", "y", "z"), model.rotate, strict=True)),
    }


def _graphic_operation(
    spec: FootprintSpec,
    layer: str,
    mode: str,
    graphics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "footprint_path": str(LIBRARY / f"{spec.name}.kicad_mod"),
        "selector": {"layer": layer},
        "mode": mode,
    }
    if graphics is not None:
        arguments["graphics"] = graphics
    return {
        "footprint": spec.name,
        "tool": "set_footprint_graphics",
        "arguments": arguments,
    }


def build_operation_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for spec in build_footprint_specs():
        path = LIBRARY / f"{spec.name}.kicad_mod"
        plan.append(
            {
                "footprint": spec.name,
                "tool": "create_footprint",
                "arguments": {
                    "output": str(path),
                    "name": spec.name,
                    "description": (
                        f"{spec.series} bottom-side hotswap socket, "
                        f"{spec.size} keycap envelope on Dwgs.User"
                    ),
                    "pads": [_pad_payload(pad) for pad in spec.pads],
                    "courtyard_clearance": spec.courtyard_clearance_mm,
                },
            }
        )
        plan.extend(
            [
                _graphic_operation(spec, "F.SilkS", "delete"),
                _graphic_operation(spec, "F.CrtYd", "delete"),
                _graphic_operation(spec, "F.Fab", "delete"),
                _graphic_operation(
                    spec, "Dwgs.User", "replace", [_keycap_graphic(spec)]
                ),
                _graphic_operation(
                    spec, "B.Fab", "replace", _body_graphics(spec)
                ),
                _graphic_operation(
                    spec, "B.CrtYd", "replace", _courtyard_graphics(spec)
                ),
                {
                    "footprint": spec.name,
                    "tool": "set_footprint_metadata",
                    "arguments": {
                        "footprint_path": str(path),
                        "description": (
                            f"{spec.series} bottom-side hotswap socket, "
                            f"{spec.size} keycap envelope on Dwgs.User"
                        ),
                        "tags": [
                            "keyboard",
                            "low_profile",
                            "hot_swap",
                            spec.series.lower().replace("-", "_"),
                            spec.size.lower(),
                        ],
                        "attributes": ["exclude_from_pos_files"],
                    },
                },
                {
                    "footprint": spec.name,
                    "tool": "set_footprint_models",
                    "arguments": {
                        "footprint_path": str(path),
                        "mode": "replace",
                        "models": [_model_payload(model) for model in spec.models],
                    },
                },
            ]
        )
    return plan


def missing_capabilities(
    schemas: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for tool_name, required_fields in REQUIRED_TOOL_FIELDS.items():
        schema = schemas.get(tool_name)
        if schema is None:
            missing[tool_name] = ["<tool>"]
            continue
        properties = schema.get("properties", {})
        absent: list[str] = []
        for field in sorted(required_fields):
            if tool_name == "create_footprint" and field in {
                "layers",
                "rotation",
                "roundrect_rratio",
            }:
                pad_properties = (
                    properties.get("pads", {})
                    .get("items", {})
                    .get("properties", {})
                )
                if field not in pad_properties:
                    absent.append(f"pad.{field}")
            elif field not in properties:
                absent.append(field)
        if absent:
            missing[tool_name] = absent
    return missing


def apply_socket_library(client: McpClient) -> None:
    schemas = client.tool_schemas("library")
    missing = missing_capabilities(schemas)
    if missing:
        raise RuntimeError(
            "Konnect cannot safely build the LH60 socket library:\n"
            + json.dumps(missing, indent=2, sort_keys=True)
        )

    LIBRARY.mkdir(parents=True, exist_ok=True)
    for operation in build_operation_plan():
        client.call_tool(operation["tool"], operation["arguments"])
        print(f"{operation['footprint']}: {operation['tool']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the LH60 G/K/Dual socket library through Konnect MCP."
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
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.plan:
        print(json.dumps(build_operation_plan(), indent=2, sort_keys=True))
        return 0
    if not args.check and not args.apply:
        print("choose --plan, --check, or --apply", file=sys.stderr)
        return 2
    with McpClient(args.konnect, args.config) as client:
        schemas = client.tool_schemas("library")
        missing = missing_capabilities(schemas)
        if missing:
            print(json.dumps(missing, indent=2, sort_keys=True), file=sys.stderr)
            return 2
        if args.check:
            print("Konnect exposes every required socket-library capability.")
            return 0
        apply_socket_library(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
