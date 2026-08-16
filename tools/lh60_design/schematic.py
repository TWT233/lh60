from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import sys

from tools.lh60_design.layout import PhysicalKey, physical_keys
from tools.lh60_design.matrix import logical_nodes
from tools.lh60_design.mcp import McpClient


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "lh60.kicad_sch"
CORE_SWITCH = "lh60-core:KeySwitch"
CORE_DIODE = "lh60-core:MatrixDiode"
CORE_TEST_POINT = "lh60-core:TestPoint"
CORE_POWER_FLAG = "lh60-core:PowerFlag"
MCU_SYMBOL = "lh60-mcu:RP2040-Tiny"
MCU_FOOTPRINT = "lh60-mcu:MCU_RP2040-Tiny_SMD"
DIODE_FOOTPRINT = "lh60-core:D_SOD-323_Bottom"
TEST_POINT_FOOTPRINT = "lh60-core:TestPoint_Pad_D1.5mm_Bottom"
RETIRED_SWITCH_REFERENCES = {
    "r3_rshift_2.75u": "SW59",
}


@dataclass(frozen=True)
class SchematicComponent:
    kind: str
    lib_id: str
    reference: str
    value: str
    footprint: str
    x: float
    y: float
    rotation: float = 0.0
    physical_key_id: str | None = None
    logical_node_id: str | None = None
    fields: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PinConnection:
    reference: str
    pin_number: str
    net_name: str


@dataclass(frozen=True)
class SchematicPlan:
    components: tuple[SchematicComponent, ...]
    connections: tuple[PinConnection, ...]


def switch_references() -> dict[str, str]:
    keys = physical_keys()
    active_ids = {key.physical_key_id for key in keys}
    reference_order = [key.physical_key_id for key in keys]
    for retired_id, reference in RETIRED_SWITCH_REFERENCES.items():
        slot = int(reference.removeprefix("SW")) - 1
        reference_order.insert(slot, retired_id)
    return {
        physical_key_id: f"SW{index + 1}"
        for index, physical_key_id in enumerate(reference_order)
        if physical_key_id in active_ids
    }


def _switch_footprint(key: PhysicalKey) -> str:
    series = (
        "Gateron-LP-or-ChocV1"
        if key.region is None
        else "Gateron-LP"
    )
    return (
        f"lh60-sockets:{series}-Hotswap-Socket-{key.footprint_size}"
    )


def _matrix_components() -> tuple[SchematicComponent, ...]:
    keys_by_id = {key.physical_key_id: key for key in physical_keys()}
    references = switch_references()
    components: list[SchematicComponent] = []
    for node in logical_nodes():
        x = 15.24 + node.column * 22.86
        y = 15.24 + node.row * 25.40
        components.append(
            SchematicComponent(
                kind="diode",
                lib_id=CORE_DIODE,
                reference=node.diode_ref,
                value="1N4148WS",
                footprint=DIODE_FOOTPRINT,
                x=x,
                y=y,
                logical_node_id=node.logical_node_id,
                fields=(("LogicalNode", node.logical_node_id),),
            )
        )
        for socket_index, physical_key_id in enumerate(node.physical_key_ids):
            key = keys_by_id[physical_key_id]
            components.append(
                SchematicComponent(
                    kind="switch",
                    lib_id=CORE_SWITCH,
                    reference=references[physical_key_id],
                    value=physical_key_id,
                    footprint=_switch_footprint(key),
                    x=x,
                    y=y + 6.35 * (socket_index + 1),
                    physical_key_id=physical_key_id,
                    logical_node_id=node.logical_node_id,
                    fields=(
                        ("PhysicalKey", physical_key_id),
                        ("LogicalNode", node.logical_node_id),
                    ),
                )
            )
    return tuple(components)


def test_point_nets() -> tuple[str, ...]:
    return (
        "VSYS",
        "3V3",
        "GND",
        *(f"COL{index}" for index in range(10)),
        *(f"ROW{index}" for index in range(7)),
        "GP27",
        "GP28",
        "GP29",
    )


def _support_components() -> tuple[SchematicComponent, ...]:
    components = [
        SchematicComponent(
            kind="mcu",
            lib_id=MCU_SYMBOL,
            reference="U1",
            value="RP2040-Tiny",
            footprint=MCU_FOOTPRINT,
            x=259.08,
            y=68.58,
        )
    ]
    for index, net_name in enumerate(test_point_nets()):
        column, row = divmod(index, 8)
        components.append(
            SchematicComponent(
                kind="test_point",
                lib_id=CORE_TEST_POINT,
                reference=f"TP{index + 1}",
                value=net_name,
                footprint=TEST_POINT_FOOTPRINT,
                x=243.84 + column * 20.32,
                y=124.46 + row * 10.16,
                fields=(("Net", net_name),),
            )
        )
    for index, net_name in enumerate(("VSYS", "3V3", "GND")):
        components.append(
            SchematicComponent(
                kind="power_flag",
                lib_id=CORE_POWER_FLAG,
                reference=f"#FLG0{index + 1}",
                value="PWR_FLAG",
                footprint="",
                x=304.80,
                y=124.46 + index * 10.16,
                fields=(("Net", net_name),),
            )
        )
    return tuple(components)


def _mcu_connections() -> tuple[PinConnection, ...]:
    connections = [
        PinConnection("U1", str(index + 1), f"COL{index}")
        for index in range(10)
    ]
    connections.extend(
        PinConnection("U1", str(index + 11), f"ROW{index}")
        for index in range(6)
    )
    connections.extend(
        (
            PinConnection("U1", "17", "ROW6"),
            PinConnection("U1", "18", "GP27"),
            PinConnection("U1", "19", "GP28"),
            PinConnection("U1", "20", "GP29"),
            PinConnection("U1", "21", "3V3"),
            PinConnection("U1", "22", "GND"),
            PinConnection("U1", "23", "VSYS"),
        )
    )
    return tuple(connections)


def _matrix_connections() -> tuple[PinConnection, ...]:
    references = switch_references()
    connections: list[PinConnection] = []
    for node in logical_nodes():
        key_net = f"KEY_{node.logical_index:02d}"
        connections.extend(
            (
                PinConnection(node.diode_ref, "2", node.column_net),
                PinConnection(node.diode_ref, "1", key_net),
            )
        )
        for physical_key_id in node.physical_key_ids:
            switch_ref = references[physical_key_id]
            connections.extend(
                (
                    PinConnection(switch_ref, "1", key_net),
                    PinConnection(switch_ref, "2", node.row_net),
                )
            )
    return tuple(connections)


def _test_point_connections() -> tuple[PinConnection, ...]:
    test_points = tuple(
        PinConnection(f"TP{index + 1}", "1", net_name)
        for index, net_name in enumerate(test_point_nets())
    )
    flags = tuple(
        PinConnection(f"#FLG0{index + 1}", "1", net_name)
        for index, net_name in enumerate(("VSYS", "3V3", "GND"))
    )
    return (*test_points, *flags)


def build_schematic_plan() -> SchematicPlan:
    components = (*_support_components(), *_matrix_components())
    connections = (
        *_mcu_connections(),
        *_matrix_connections(),
        *_test_point_connections(),
    )
    return SchematicPlan(
        components=tuple(components),
        connections=tuple(connections),
    )


def _placement_payload(component: SchematicComponent) -> dict[str, object]:
    return {
        "lib_id": component.lib_id,
        "reference": component.reference,
        "value": component.value,
        "x": component.x,
        "y": component.y,
        "rotation": component.rotation,
    }


def _edit_payload(component: SchematicComponent) -> dict[str, object]:
    payload: dict[str, object] = {
        "reference": component.reference,
        "value": component.value,
        "footprint": component.footprint,
    }
    if component.fields:
        payload["fields"] = dict(component.fields)
    return payload


def _connections_by_net(
    connections: tuple[PinConnection, ...],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for connection in connections:
        grouped[connection.net_name].append(
            {
                "reference": connection.reference,
                "pin_number": connection.pin_number,
            }
        )
    return dict(grouped)


def apply_schematic(
    client: McpClient,
    schematic: Path = SCHEMATIC,
) -> None:
    plan = build_schematic_plan()
    client.tool_schemas("sch_batch")
    client.call_tool(
        "batch_place_components",
        {
            "schematic": str(schematic),
            "components": [
                _placement_payload(component)
                for component in plan.components
            ],
        },
    )
    client.call_tool(
        "batch_edit_schematic_components",
        {
            "schematic": str(schematic),
            "edits": [
                _edit_payload(component)
                for component in plan.components
            ],
        },
    )
    for net_name, pins in _connections_by_net(plan.connections).items():
        client.call_tool(
            "batch_connect_to_net",
            {
                "schematic": str(schematic),
                "net_name": net_name,
                "pins": pins,
            },
        )
    client.tool_schemas("sch_components")
    client.call_tool(
        "update_symbols_from_library",
        {
            "schematic": str(schematic),
            "dry_run": False,
            "allow_pin_moves": False,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the complete LH60 production schematic through Konnect."
    )
    parser.add_argument(
        "--schematic",
        type=Path,
        default=SCHEMATIC,
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
        apply_schematic(client, args.schematic)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
