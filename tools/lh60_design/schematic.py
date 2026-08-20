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
CORE_SWITCH = "Switch:SW_Push"
CORE_DIODE = "Device:D"
CORE_POWER_FLAG = "lh60-core:PowerFlag"
MCU_SYMBOL = "lh60-mcu:RP2040-Tiny"
MCU_FOOTPRINT = "lh60-mcu:MCU_RP2040-Tiny_SMD"
DIODE_FOOTPRINT = "lh60-core:D_SOD-323_Bottom"
PAGE_SIZE = "A3"
PAGE_PORTRAIT = False
MATRIX_X0_MM = 20.32
MATRIX_Y0_MM = 20.32
MATRIX_X_PITCH_MM = 30.48
MATRIX_Y_PITCH_MM = 33.02
SWITCH_Y_OFFSETS_MM = (10.16, 17.78)
MCU_POSITION_MM = (350.52, 45.72)
CONNECTOR_POSITIONS_MM = {
    "J1": (330.20, 96.52),
    "J2": (330.20, 134.62),
    "J3": (330.20, 177.80),
    "J4": (373.38, 134.62),
    "J5": (373.38, 175.26),
    "J6": (373.38, 215.90),
}
POWER_FLAG_POSITIONS_MM = {
    "#FLG01": (381.00, 86.36),
    "#FLG02": (381.00, 106.68),
    "#FLG03": (381.00, 127.00),
}
RETIRED_SWITCH_REFERENCES = {
    "r3_rshift_2.75u": "SW59",
}
POWER_FLAG_INSTANCE_FLAGS = {
    "#FLG01": {"in_bom": True, "on_board": False, "dnp": False},
    "#FLG02": {"in_bom": True, "on_board": False, "dnp": False},
    "#FLG03": {"in_bom": True, "on_board": False, "dnp": False},
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
    in_bom: bool | None = None
    on_board: bool | None = None
    dnp: bool | None = None


@dataclass(frozen=True)
class PinConnection:
    reference: str
    pin_number: str
    net_name: str


@dataclass(frozen=True)
class ConnectorGroup:
    reference: str
    value: str
    lib_id: str
    footprint: str
    pin_map: tuple[tuple[str, str], ...]
    x: float
    y: float


@dataclass(frozen=True)
class FieldVisibility:
    reference: str
    reference_visible: bool
    value_visible: bool


@dataclass(frozen=True)
class SchematicPlan:
    components: tuple[SchematicComponent, ...]
    connections: tuple[PinConnection, ...]
    page_size: str
    portrait: bool
    field_visibility: tuple[FieldVisibility, ...]


CONNECTOR_GROUPS = (
    ConnectorGroup(
        reference="J1",
        value="PWR",
        lib_id="lh60-core:Conn_01x03",
        footprint="lh60-core:PinHeader_1x03_P2.54mm_Vertical",
        pin_map=(("1", "VSYS"), ("2", "3V3"), ("3", "GND")),
        x=CONNECTOR_POSITIONS_MM["J1"][0],
        y=CONNECTOR_POSITIONS_MM["J1"][1],
    ),
    ConnectorGroup(
        reference="J2",
        value="COL_A",
        lib_id="lh60-core:Conn_01x05",
        footprint="lh60-core:PinHeader_1x05_P2.54mm_Vertical",
        pin_map=(
            ("1", "COL0"),
            ("2", "COL1"),
            ("3", "COL2"),
            ("4", "COL3"),
            ("5", "COL4"),
        ),
        x=CONNECTOR_POSITIONS_MM["J2"][0],
        y=CONNECTOR_POSITIONS_MM["J2"][1],
    ),
    ConnectorGroup(
        reference="J3",
        value="COL_B",
        lib_id="lh60-core:Conn_01x05",
        footprint="lh60-core:PinHeader_1x05_P2.54mm_Vertical",
        pin_map=(
            ("1", "COL5"),
            ("2", "COL6"),
            ("3", "COL7"),
            ("4", "COL8"),
            ("5", "COL9"),
        ),
        x=CONNECTOR_POSITIONS_MM["J3"][0],
        y=CONNECTOR_POSITIONS_MM["J3"][1],
    ),
    ConnectorGroup(
        reference="J4",
        value="ROW_A",
        lib_id="lh60-core:Conn_01x04",
        footprint="lh60-core:PinHeader_1x04_P2.54mm_Vertical",
        pin_map=(("1", "ROW0"), ("2", "ROW1"), ("3", "ROW2"), ("4", "ROW3")),
        x=CONNECTOR_POSITIONS_MM["J4"][0],
        y=CONNECTOR_POSITIONS_MM["J4"][1],
    ),
    ConnectorGroup(
        reference="J5",
        value="ROW_B",
        lib_id="lh60-core:Conn_01x03",
        footprint="lh60-core:PinHeader_1x03_P2.54mm_Vertical",
        pin_map=(("1", "ROW4"), ("2", "ROW5"), ("3", "ROW6")),
        x=CONNECTOR_POSITIONS_MM["J5"][0],
        y=CONNECTOR_POSITIONS_MM["J5"][1],
    ),
    ConnectorGroup(
        reference="J6",
        value="AUX",
        lib_id="lh60-core:Conn_01x03",
        footprint="lh60-core:PinHeader_1x03_P2.54mm_Vertical",
        pin_map=(("1", "GP27"), ("2", "GP28"), ("3", "GP29")),
        x=CONNECTOR_POSITIONS_MM["J6"][0],
        y=CONNECTOR_POSITIONS_MM["J6"][1],
    ),
)


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
        x = MATRIX_X0_MM + node.column * MATRIX_X_PITCH_MM
        y = MATRIX_Y0_MM + node.row * MATRIX_Y_PITCH_MM
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
        if len(node.physical_key_ids) > len(SWITCH_Y_OFFSETS_MM):
            raise ValueError("switch offsets are exhausted")
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
                    y=y + SWITCH_Y_OFFSETS_MM[socket_index],
                    physical_key_id=physical_key_id,
                    logical_node_id=node.logical_node_id,
                    fields=(
                        ("PhysicalKey", physical_key_id),
                        ("LogicalNode", node.logical_node_id),
                    ),
                )
            )
    return tuple(components)


def _support_components() -> tuple[SchematicComponent, ...]:
    components = [
        SchematicComponent(
            kind="mcu",
            lib_id=MCU_SYMBOL,
            reference="U1",
            value="RP2040-Tiny",
            footprint=MCU_FOOTPRINT,
            x=MCU_POSITION_MM[0],
            y=MCU_POSITION_MM[1],
        )
    ]
    for group in CONNECTOR_GROUPS:
        components.append(
            SchematicComponent(
                kind="connector",
                lib_id=group.lib_id,
                reference=group.reference,
                value=group.value,
                footprint=group.footprint,
                x=group.x,
                y=group.y,
            )
        )
    for reference, net_name in (
        ("#FLG01", "VSYS"),
        ("#FLG02", "3V3"),
        ("#FLG03", "GND"),
    ):
        flags = POWER_FLAG_INSTANCE_FLAGS[reference]
        components.append(
            SchematicComponent(
                kind="power_flag",
                lib_id=CORE_POWER_FLAG,
                reference=reference,
                value="PWR_FLAG",
                footprint="",
                x=POWER_FLAG_POSITIONS_MM[reference][0],
                y=POWER_FLAG_POSITIONS_MM[reference][1],
                in_bom=flags["in_bom"],
                on_board=flags["on_board"],
                dnp=flags["dnp"],
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


def _connector_connections() -> tuple[PinConnection, ...]:
    return tuple(
        PinConnection(group.reference, pin_number, net_name)
        for group in CONNECTOR_GROUPS
        for pin_number, net_name in group.pin_map
    )


def _power_flag_connections() -> tuple[PinConnection, ...]:
    return tuple(
        PinConnection(reference, "1", net_name)
        for reference, net_name in (
            ("#FLG01", "VSYS"),
            ("#FLG02", "3V3"),
            ("#FLG03", "GND"),
        )
    )


def _field_visibility() -> tuple[FieldVisibility, ...]:
    switches = sorted(
        (
            component.reference
            for component in _matrix_components()
            if component.kind == "switch"
        ),
        key=lambda reference: int(reference.removeprefix("SW")),
    )
    return tuple(
        [FieldVisibility(f"D{index}", False, False) for index in range(1, 71)]
        + [FieldVisibility(reference, False, True) for reference in switches]
        + [FieldVisibility(group.reference, True, True) for group in CONNECTOR_GROUPS]
        + [FieldVisibility("U1", True, True)]
    )


def build_schematic_plan() -> SchematicPlan:
    components = (*_support_components(), *_matrix_components())
    connections = (
        *_mcu_connections(),
        *_matrix_connections(),
        *_connector_connections(),
        *_power_flag_connections(),
    )
    return SchematicPlan(
        components=tuple(components),
        connections=tuple(connections),
        page_size=PAGE_SIZE,
        portrait=PAGE_PORTRAIT,
        field_visibility=_field_visibility(),
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


def _instance_flag_payload(component: SchematicComponent) -> dict[str, object] | None:
    if (
        component.in_bom is None
        and component.on_board is None
        and component.dnp is None
    ):
        return None
    payload: dict[str, object] = {"reference": component.reference}
    if component.in_bom is not None:
        payload["in_bom"] = component.in_bom
    if component.on_board is not None:
        payload["on_board"] = component.on_board
    if component.dnp is not None:
        payload["dnp"] = component.dnp
    return payload


def _field_visibility_payload(
    visibility: FieldVisibility,
) -> dict[str, object]:
    return {
        "reference": visibility.reference,
        "reference_visible": visibility.reference_visible,
        "value_visible": visibility.value_visible,
    }


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


def _call_tool_json(
    client: McpClient,
    name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    result = client.call_tool(name, arguments)
    return McpClient.result_json(result)


def _count_items(values: object, target: str) -> int:
    if not isinstance(values, list):
        return 0
    return sum(1 for value in values if value == target)


def _require_empty_list_result(
    result: dict[str, object],
    key: str,
    tool: str,
) -> None:
    values = result.get(key, [])
    if not isinstance(values, list):
        raise RuntimeError(f"{tool} returned non-list {key}: {values!r}")
    if values:
        raise RuntimeError(f"{tool} reported {key}: {values}")


def _require_single_accounting(
    result: dict[str, object],
    *,
    target: str,
    updated_key: str,
    unchanged_key: str,
    tool: str,
) -> None:
    updated_count = _count_items(result.get(updated_key, []), target)
    unchanged_count = _count_items(result.get(unchanged_key, []), target)
    if updated_count + unchanged_count != 1:
        raise RuntimeError(
            f"{tool} expected exactly one accounting entry for {target}, "
            f"got {updated_key}={updated_count} {unchanged_key}={unchanged_count}"
        )


def _refresh_u1_from_library(
    client: McpClient,
    schematic: Path,
) -> None:
    result = _call_tool_json(
        client,
        "update_symbols_from_library",
        {
            "schematic": str(schematic),
            "references": ["U1"],
            "dry_run": False,
            "allow_pin_moves": True,
        },
    )
    _require_empty_list_result(result, "errors", "update_symbols_from_library")
    _require_empty_list_result(result, "pins_moved", "update_symbols_from_library")
    _require_single_accounting(
        result,
        target=MCU_SYMBOL,
        updated_key="updated",
        unchanged_key="unchanged",
        tool="update_symbols_from_library",
    )


def _reset_u1_field_positions(
    client: McpClient,
    schematic: Path,
) -> None:
    result = _call_tool_json(
        client,
        "reset_schematic_field_positions",
        {
            "schematic": str(schematic),
            "references": ["U1"],
            "dry_run": False,
        },
    )
    for key in ("no_library_anchor", "no_property", "not_found"):
        _require_empty_list_result(result, key, "reset_schematic_field_positions")
    for field_name in ("U1.Reference", "U1.Value"):
        _require_single_accounting(
            result,
            target=field_name,
            updated_key="moved",
            unchanged_key="unchanged",
            tool="reset_schematic_field_positions",
        )


def _verify_final_symbol_refresh(
    client: McpClient,
    schematic: Path,
) -> None:
    result = _call_tool_json(
        client,
        "update_symbols_from_library",
        {
            "schematic": str(schematic),
            "dry_run": False,
            "allow_pin_moves": False,
        },
    )
    _require_empty_list_result(result, "errors", "update_symbols_from_library")
    _require_empty_list_result(result, "pins_moved", "update_symbols_from_library")


def apply_power_flag_instance_flags(
    client: McpClient,
    schematic: Path = SCHEMATIC,
) -> dict[str, object]:
    plan = build_schematic_plan()
    edits = [
        payload
        for component in plan.components
        if (payload := _instance_flag_payload(component)) is not None
    ]
    result = _call_tool_json(
        client,
        "batch_edit_schematic_components",
        {
            "schematic": str(schematic),
            "edits": edits,
        },
    )
    if result.get("atomic") is not True:
        raise RuntimeError("batch_edit_schematic_components did not complete atomically")
    updated = result.get("updated", [])
    unchanged = result.get("unchanged", [])
    if not isinstance(updated, list) or not isinstance(unchanged, list):
        raise RuntimeError("batch_edit_schematic_components accounting must be lists")
    if result.get("updated_count") != len(updated):
        raise RuntimeError("batch_edit_schematic_components updated_count mismatch")
    if len(updated) + len(unchanged) != len(edits):
        raise RuntimeError("batch_edit_schematic_components accounting mismatch")
    expected = {reference: dict(flags) for reference, flags in POWER_FLAG_INSTANCE_FLAGS.items()}
    seen = []
    for key, entries in (("updated", updated), ("unchanged", unchanged)):
        for item in entries:
            if isinstance(item, str):
                reference = item
                flags = expected.get(reference)
                changed_flags = []
            elif isinstance(item, dict):
                reference = item.get("reference")
                flags = item.get("flags", expected.get(str(reference)))
                changed_flags = item.get("changed_flags", [])
            else:
                raise RuntimeError(f"batch_edit_schematic_components {key} entry is invalid: {item!r}")
            if reference not in expected:
                raise RuntimeError(f"batch_edit_schematic_components returned unexpected reference: {reference!r}")
            if flags != expected[reference]:
                raise RuntimeError(f"batch_edit_schematic_components final flags mismatch for {reference}")
            if not isinstance(changed_flags, list):
                raise RuntimeError(f"batch_edit_schematic_components changed_flags mismatch for {reference}")
            invalid_changed_flags = set(changed_flags) - {"dnp", "in_bom", "on_board"}
            if invalid_changed_flags:
                raise RuntimeError(f"batch_edit_schematic_components changed_flags mismatch for {reference}")
            seen.append(str(reference))
    if len(seen) != len(set(seen)):
        raise RuntimeError("batch_edit_schematic_components references must be unique")
    if set(seen) != set(expected):
        raise RuntimeError(
            f"batch_edit_schematic_components accounting mismatch: seen={sorted(seen)}, expected={sorted(expected)}"
        )
    return result


def _require_nested_flag_edit_schema(schema: dict[str, object]) -> None:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise RuntimeError("Konnect schematic input contract mismatch: batch_edit_schematic_components properties missing")
    edits = properties.get("edits")
    if not isinstance(edits, dict):
        raise RuntimeError("Konnect schematic input contract mismatch: batch_edit_schematic_components.edits missing")
    items = edits.get("items")
    if not isinstance(items, dict):
        raise RuntimeError("Konnect schematic input contract mismatch: batch_edit_schematic_components.edits.items missing")
    item_properties = items.get("properties")
    if not isinstance(item_properties, dict):
        raise RuntimeError(
            "Konnect schematic input contract mismatch: batch_edit_schematic_components.edits.items.properties missing"
        )
    for flag in ("in_bom", "on_board", "dnp"):
        descriptor = item_properties.get(flag)
        if not isinstance(descriptor, dict) or descriptor.get("type") != "boolean":
            raise RuntimeError(
                "Konnect schematic input contract mismatch: "
                f"batch_edit_schematic_components nested flag {flag} missing or not boolean"
            )


def require_schematic_capabilities(client: McpClient) -> None:
    """Fail closed unless the deployed Konnect supports every A3 apply step."""
    schemas = {
        toolset: client.tool_schemas(toolset)
        for toolset in ("sch_batch", "sch_wiring", "sch_components", "library")
    }
    required = {
        "sch_batch": {
            "batch_delete_schematic_components",
            "batch_delete",
            "batch_place_components",
            "batch_edit_schematic_components",
            "batch_connect_to_net",
            "batch_set_schematic_field_visibility",
        },
        "sch_wiring": {"batch_delete_schematic_wire"},
        "sch_components": {
            "get_schematic_component",
            "list_schematic_components",
            "set_schematic_page",
            "update_symbols_from_library",
            "reset_schematic_field_positions",
        },
        "library": {"create_symbol"},
    }
    missing = {
        toolset: sorted(names - schemas[toolset].keys())
        for toolset, names in required.items()
        if names - schemas[toolset].keys()
    }
    if missing:
        raise RuntimeError(f"missing Konnect schematic tools: {missing}")
    contracts = {
        "batch_delete_schematic_components": ("sch_batch", ("schematic", "references"), ("schematic", "references")),
        "batch_delete": ("sch_batch", ("schematic",), ("schematic", "uuids")),
        "batch_delete_schematic_wire": ("sch_wiring", ("schematic", "uuids"), ("schematic", "uuids")),
        "set_schematic_page": ("sch_components", ("schematic", "size"), ("schematic", "size", "portrait")),
        "batch_place_components": ("sch_batch", ("schematic", "components"), ("schematic", "components")),
        "batch_edit_schematic_components": ("sch_batch", ("schematic", "edits"), ("schematic", "edits")),
        "batch_connect_to_net": ("sch_batch", ("schematic", "net_name", "pins"), ("schematic", "net_name", "pins")),
        "batch_set_schematic_field_visibility": ("sch_batch", ("schematic", "edits"), ("schematic", "edits")),
        "update_symbols_from_library": (
            "sch_components",
            ("schematic",),
            ("schematic", "dry_run", "allow_pin_moves", "references"),
        ),
        "reset_schematic_field_positions": (
            "sch_components",
            ("schematic",),
            ("schematic", "dry_run", "references"),
        ),
        "create_symbol": ("library", ("library_path", "name", "reference_prefix"), ("reference_at", "value_at")),
    }
    missing_inputs = {}
    for tool, (toolset, required_inputs, property_inputs) in contracts.items():
        schema = schemas[toolset][tool]
        missing_required = sorted(set(required_inputs) - set(schema.get("required", [])))
        missing_properties = sorted(set(property_inputs) - set(schema.get("properties", {})))
        if missing_required or missing_properties:
            missing_inputs[tool] = {
                "required": missing_required,
                "properties": missing_properties,
            }
    if missing_inputs:
        raise RuntimeError(f"Konnect schematic input contract mismatch: {missing_inputs}")
    _require_nested_flag_edit_schema(schemas["sch_batch"]["batch_edit_schematic_components"])


def apply_schematic(
    client: McpClient,
    schematic: Path = SCHEMATIC,
) -> None:
    plan = build_schematic_plan()
    require_schematic_capabilities(client)
    client.call_tool(
        "set_schematic_page",
        {
            "schematic": str(schematic),
            "size": plan.page_size,
            "portrait": plan.portrait,
        },
    )
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
    _refresh_u1_from_library(client, schematic)
    _reset_u1_field_positions(client, schematic)
    for net_name, pins in _connections_by_net(plan.connections).items():
        client.call_tool(
            "batch_connect_to_net",
            {
                "schematic": str(schematic),
                "net_name": net_name,
                "pins": pins,
            },
        )
    client.call_tool(
        "batch_set_schematic_field_visibility",
        {
            "schematic": str(schematic),
            "edits": [
                _field_visibility_payload(visibility)
                for visibility in plan.field_visibility
            ],
        },
    )
    _verify_final_symbol_refresh(client, schematic)
    apply_power_flag_instance_flags(client, schematic)


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
