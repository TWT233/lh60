from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from shapely import affinity
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "lib" / "lh60-sockets"
DUAL_NAME = "Gateron-LP-or-ChocV1-Hotswap-Socket-1U"
GATERON_NAMES = (
    "Gateron-LP-Hotswap-Socket-1U",
    "Gateron-LP-Hotswap-Socket-1.25U",
    "Gateron-LP-Hotswap-Socket-1.5U",
    "Gateron-LP-Hotswap-Socket-1.75U",
    "Gateron-LP-Hotswap-Socket-2U",
    "Gateron-LP-Hotswap-Socket-2.25U",
    "Gateron-LP-Hotswap-Socket-2.75U",
)
ALL_NAMES = (*GATERON_NAMES, DUAL_NAME)
KEYCAP_WIDTHS = {
    "Gateron-LP-Hotswap-Socket-1U": 19.05,
    "Gateron-LP-Hotswap-Socket-1.25U": 23.8125,
    "Gateron-LP-Hotswap-Socket-1.5U": 28.575,
    "Gateron-LP-Hotswap-Socket-1.75U": 33.3375,
    "Gateron-LP-Hotswap-Socket-2U": 38.1,
    "Gateron-LP-Hotswap-Socket-2.25U": 42.8625,
    "Gateron-LP-Hotswap-Socket-2.75U": 52.3875,
    DUAL_NAME: 19.05,
}

REQUIRED_TOOL_FIELDS = {
    "edit_footprint_pad": {
        "footprint_path",
        "pad_number",
        "new_number",
        "match_all",
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


def rounded_rectangle(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    radius: float,
) -> Polygon:
    left = center_x - width / 2
    right = center_x + width / 2
    bottom = center_y - height / 2
    top = center_y + height / 2
    horizontal = box(left + radius, bottom, right - radius, top)
    vertical = box(left, bottom + radius, right, top - radius)
    corners = [
        Point(x, y).buffer(radius, quad_segs=8)
        for x in (left + radius, right - radius)
        for y in (bottom + radius, top - radius)
    ]
    return unary_union([horizontal, vertical, *corners])


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


def sample_arc(
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
    if middle_sweep <= counter_clockwise_sweep:
        sweep = counter_clockwise_sweep
    else:
        sweep = -((start_angle - end_angle) % (2 * math.pi))

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
    points.extend(sample_arc(points[-1], middle, end)[1:])


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
    terminals = [
        box(-8.445, 3.615, -6.815, 5.785),
        box(5.025, 4.665, 6.655, 6.835),
    ]
    return unary_union([body, *terminals])


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
    body = Polygon(points)
    terminals = [
        box(-9.075, 2.96, -7.275, 4.64),
        box(2.275, 5.06, 4.075, 6.74),
    ]
    return unary_union([body, *terminals])


def gateron_land_pattern() -> Polygon:
    return unary_union(
        [
            rounded_rectangle(-8.075, 4.7, 2.5, 2.55, 0.5),
            box(-8.3, 4.2, -4.4, 5.2),
            Point(-4.4, 4.7).buffer(2, quad_segs=16),
            Point(2.6, 5.75).buffer(2, quad_segs=16),
            box(2.6, 5.25, 6.35, 6.25),
            rounded_rectangle(6.275, 5.75, 2.5, 2.55, 0.5),
        ]
    )


def choc_land_pattern() -> Polygon:
    return unary_union(
        [
            Point(0, -5.9).buffer(2, quad_segs=16),
            box(-3.95, -6.4, 0, -5.4),
            rounded_rectangle(-3.7, -5.9, 2.6, 2.6, 0.52),
            Point(5, -3.8).buffer(2, quad_segs=16),
            box(5, -4.3, 8.95, -3.3),
            rounded_rectangle(8.7, -3.8, 2.6, 2.6, 0.52),
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


def gateron_courtyard_polygons() -> list[Polygon]:
    geometry = unary_union([gateron_physical_geometry(), gateron_land_pattern()])
    return _polygons(geometry.buffer(0.25, quad_segs=8, join_style="round"))


def choc_courtyard_polygons() -> list[Polygon]:
    rotated_body = affinity.rotate(choc_physical_geometry(), 180, origin=(0, 0))
    geometry = unary_union([rotated_body, choc_land_pattern()])
    return _polygons(geometry.buffer(0.25, quad_segs=8, join_style="round"))


def _rounded(value: float) -> float:
    rounded = round(value, 3)
    return 0.0 if rounded == -0.0 else rounded


def polygon_graphics(
    polygons: Iterable[Polygon],
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
        for polygon in polygons
    ]


def keycap_graphic(name: str) -> dict[str, Any]:
    half_width = KEYCAP_WIDTHS[name] / 2
    return {
        "type": "rect",
        "start": {"x": _rounded(-half_width), "y": -9.525},
        "end": {"x": _rounded(half_width), "y": 9.525},
        "stroke_width_mm": 0.12,
        "fill": "none",
    }


def mark_graphics(letter: str, origin_x: float, origin_y: float) -> list[dict[str, Any]]:
    lines = {
        "G": [
            ((0.8, 0), (0, 0)),
            ((0, 0), (0, 1.4)),
            ((0, 1.4), (0.8, 1.4)),
            ((0.8, 1.4), (0.8, 0.8)),
            ((0.8, 0.8), (0.45, 0.8)),
        ],
        "C": [
            ((0.8, 0), (0, 0)),
            ((0, 0), (0, 1.4)),
            ((0, 1.4), (0.8, 1.4)),
        ],
    }[letter]
    return [
        {
            "type": "line",
            "start": {"x": _rounded(origin_x + start[0]), "y": _rounded(origin_y + start[1])},
            "end": {"x": _rounded(origin_x + end[0]), "y": _rounded(origin_y + end[1])},
            "stroke_width_mm": 0.1,
        }
        for start, end in lines
    ]


def _graphic_operation(
    name: str,
    layer: str,
    mode: str,
    graphics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "footprint_path": str(LIBRARY / f"{name}.kicad_mod"),
        "selector": {"layer": layer},
        "mode": mode,
    }
    if graphics is not None:
        arguments["graphics"] = graphics
    return {
        "footprint": name,
        "tool": "set_footprint_graphics",
        "arguments": arguments,
    }


def _gateron_models() -> list[dict[str, Any]]:
    return [
        {
            "path": "../mxv2/Gateron_KS33_Hotswap.pretty/Gateron-KS33-Socket.step",
            "offset": {"x": 5.025, "y": -7.925, "z": -1.838},
            "scale": {"x": -1, "y": 1, "z": 1},
            "rotate": {"x": -90, "y": 0, "z": 0},
        }
    ]


def _choc_models() -> list[dict[str, Any]]:
    return [
        {
            "path": "../mxv2/Kailh_PG1353_Hotswap.pretty/Kailh-Choc-Socket-CPG135001S30.step",
            "offset": {"x": 0, "y": 0, "z": 0},
            "scale": {"x": -1, "y": 1, "z": 1},
            "rotate": {"x": 90, "y": 0, "z": 0},
        }
    ]


def build_operation_plan() -> list[dict[str, Any]]:
    gateron_fab = polygon_graphics(_polygons(gateron_physical_geometry()), 0.1)
    gateron_fab.extend(mark_graphics("G", -1.0, 4.2))
    gateron_courtyard = polygon_graphics(gateron_courtyard_polygons(), 0.05)
    rotated_choc = affinity.rotate(choc_physical_geometry(), 180, origin=(0, 0))
    choc_fab = polygon_graphics(_polygons(rotated_choc), 0.1)
    choc_fab.extend(mark_graphics("C", -0.4, -7.0))
    choc_courtyard = polygon_graphics(choc_courtyard_polygons(), 0.05)

    operations: list[dict[str, Any]] = [
        {
            "footprint": DUAL_NAME,
            "tool": "edit_footprint_pad",
            "arguments": {
                "footprint_path": str(LIBRARY / f"{DUAL_NAME}.kicad_mod"),
                "pad_number": "3",
                "new_number": "1",
                "match_all": True,
            },
        },
        {
            "footprint": DUAL_NAME,
            "tool": "edit_footprint_pad",
            "arguments": {
                "footprint_path": str(LIBRARY / f"{DUAL_NAME}.kicad_mod"),
                "pad_number": "4",
                "new_number": "2",
                "match_all": True,
            },
        },
    ]

    for name in ALL_NAMES:
        is_dual = name == DUAL_NAME
        operations.extend(
            [
                _graphic_operation(name, "F.SilkS", "delete"),
                _graphic_operation(name, "Dwgs.User", "replace", [keycap_graphic(name)]),
                _graphic_operation(
                    name,
                    "B.Fab",
                    "replace",
                    [*gateron_fab, *choc_fab] if is_dual else gateron_fab,
                ),
                _graphic_operation(
                    name,
                    "B.CrtYd",
                    "replace",
                    [*gateron_courtyard, *choc_courtyard]
                    if is_dual
                    else gateron_courtyard,
                ),
                {
                    "footprint": name,
                    "tool": "set_footprint_metadata",
                    "arguments": {
                        "footprint_path": str(LIBRARY / f"{name}.kicad_mod"),
                        "description": (
                            "Gateron LP or Choc V1 bottom-side hotswap socket, "
                            "plated contact holes, 1U keycap envelope on Dwgs.User"
                            if is_dual
                            else "Gateron LP bottom-side hotswap socket, plated "
                            "contact holes, keycap envelope on Dwgs.User"
                        ),
                        "tags": [
                            "keyboard",
                            "gateron",
                            "low_profile",
                            "hot_swap",
                            *(["choc_v1", "dual_socket"] if is_dual else []),
                        ],
                        "attributes": ["exclude_from_pos_files"],
                    },
                },
                {
                    "footprint": name,
                    "tool": "set_footprint_models",
                    "arguments": {
                        "footprint_path": str(LIBRARY / f"{name}.kicad_mod"),
                        "mode": "replace",
                        "models": [
                            *_gateron_models(),
                            *(_choc_models() if is_dual else []),
                        ],
                    },
                },
            ]
        )
    return operations


class McpClient:
    def __init__(self, binary: Path, config: Path) -> None:
        self.process = subprocess.Popen(
            [str(binary), "--config", str(config)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.next_id = 1
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "lh60-socket-updater", "version": "1"},
            },
        )
        self.notify("notifications/initialized")

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        if not self.process.stdin or not self.process.stdout:
            raise RuntimeError("Konnect stdio is unavailable")
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        while line := self.process.stdout.readline():
            response = json.loads(line)
            if response.get("id") == request_id:
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response
        raise RuntimeError("Konnect closed stdout")

    def notify(self, method: str) -> None:
        if not self.process.stdin:
            raise RuntimeError("Konnect stdin is unavailable")
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.process.stdin.flush()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self.request(
            "tools/call", {"name": name, "arguments": arguments}
        )["result"]
        if response.get("isError"):
            message = response.get("content", [{}])[0].get("text", response)
            raise RuntimeError(f"{name} failed: {message}")
        return response

    def close(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=5)

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def tool_schemas(client: McpClient) -> dict[str, dict[str, Any]]:
    client.call_tool("load_toolset", {"name": "library"})
    tools = client.request("tools/list", {})["result"]["tools"]
    return {tool["name"]: tool["inputSchema"] for tool in tools}


def missing_capabilities(
    schemas: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    return missing_capabilities_for(REQUIRED_TOOL_FIELDS, schemas)


def missing_capabilities_for(
    required_tool_fields: dict[str, set[str]],
    schemas: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for name, required_fields in required_tool_fields.items():
        if name not in schemas:
            missing[name] = ["<tool>"]
            continue
        properties = set(schemas[name].get("properties", {}))
        absent = sorted(required_fields - properties)
        if absent:
            missing[name] = absent
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely update LH60 socket footprints through Konnect MCP."
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
        "--plan",
        action="store_true",
        help="Print the deterministic MCP operation plan without connecting.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Konnect capability without writing.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply all footprint operations after capability validation.",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(REQUIRED_TOOL_FIELDS),
        help="Limit --check or --apply to one mutation tool; may be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_operation_plan()
    selected_tools = set(args.only or REQUIRED_TOOL_FIELDS)
    selected_plan = [
        operation for operation in plan if operation["tool"] in selected_tools
    ]
    if args.plan:
        print(json.dumps(selected_plan, indent=2, sort_keys=True))
        return 0
    if not args.check and not args.apply:
        print("choose one of --plan, --check, or --apply", file=sys.stderr)
        return 2

    with McpClient(args.konnect, args.config) as client:
        schemas = tool_schemas(client)
        required_fields = {
            name: fields
            for name, fields in REQUIRED_TOOL_FIELDS.items()
            if name in selected_tools
        }
        missing = missing_capabilities_for(required_fields, schemas)
        if missing:
            print(
                "Konnect cannot safely apply the LH60 socket update:\n"
                + json.dumps(missing, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 2
        if args.check:
            print("Konnect exposes every required safe mutation.")
            return 0
        for operation in selected_plan:
            client.call_tool(operation["tool"], operation["arguments"])
            print(f"{operation['footprint']}: {operation['tool']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
