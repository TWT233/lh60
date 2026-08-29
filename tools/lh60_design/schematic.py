from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
import sys

from tools.lh60_design.interconnect import interboard_contract
from tools.lh60_design.layout import PhysicalKey, physical_keys
from tools.lh60_design.matrix import logical_nodes
from tools.lh60_design.mcp import McpClient


ROOT = Path(__file__).resolve().parents[2]
SCHEMATIC = ROOT / "lh60.kicad_sch"
CORE_SWITCH = "Switch:SW_Push"
CORE_DIODE = "Device:D"
DIODE_FOOTPRINT = "lh60-core:D_SOD-323_Bottom"
FFC_SYMBOL = "lh60-interconnect:FPC-05F-24PH20"
FFC_FOOTPRINT = "lh60-interconnect:FPC-05F-24PH20"
PAGE_SIZE = "A3"
PAGE_PORTRAIT = False
MATRIX_X0_MM = 20.32
MATRIX_Y0_MM = 20.32
MATRIX_X_PITCH_MM = 30.48
MATRIX_Y_PITCH_MM = 33.02
SWITCH_Y_OFFSETS_MM = (10.16, 17.78)
FFC_POSITION_MM = (360.68, 45.72)
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
    in_bom: bool | None = None
    on_board: bool | None = None
    dnp: bool | None = None


@dataclass(frozen=True)
class PinConnection:
    reference: str
    pin_number: str
    net_name: str


@dataclass(frozen=True)
class NoConnectPin:
    reference: str
    pin_number: str


@dataclass(frozen=True)
class FieldVisibility:
    reference: str
    reference_visible: bool
    value_visible: bool


@dataclass(frozen=True)
class SchematicPlan:
    components: tuple[SchematicComponent, ...]
    connections: tuple[PinConnection, ...]
    no_connects: tuple[NoConnectPin, ...]
    page_size: str
    portrait: bool
    field_visibility: tuple[FieldVisibility, ...]


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
    connector = interboard_contract().connector
    return (
        SchematicComponent(
            kind="connector",
            lib_id=FFC_SYMBOL,
            reference="J1",
            value=connector.mpn,
            footprint=FFC_FOOTPRINT,
            x=FFC_POSITION_MM[0],
            y=FFC_POSITION_MM[1],
            fields=(
                ("Manufacturer", connector.manufacturer),
                ("MPN", connector.mpn),
                ("LCSC", connector.lcsc_part),
            ),
        ),
    )


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


def _ffc_connections() -> tuple[PinConnection, ...]:
    contract = interboard_contract()
    return tuple(
        PinConnection("J1", str(pin.number), pin.net_name)
        for pin in contract.pins
        if pin.net_name is not None
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
        + [FieldVisibility("J1", True, True)]
    )


def build_schematic_plan() -> SchematicPlan:
    components = (*_support_components(), *_matrix_components())
    connections = (
        *_matrix_connections(),
        *_ffc_connections(),
    )
    return SchematicPlan(
        components=tuple(components),
        connections=tuple(connections),
        no_connects=(NoConnectPin("J1", "23"),),
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
    if component.lib_id not in {CORE_SWITCH, CORE_DIODE} and component.fields:
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
    edits: list[dict[str, object]] = []
    if not edits:
        return {"atomic": True, "updated_count": 0, "updated": [], "unchanged": []}
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
    expected: dict[str, dict[str, object]] = {}
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
        for toolset in ("sch_batch", "sch_wiring", "sch_components")
    }
    required = {
        "sch_batch": {
            "batch_delete_schematic_components",
            "batch_delete",
            "batch_place_components",
            "batch_edit_schematic_components",
            "batch_connect_to_net",
        },
        "sch_wiring": {"batch_add_no_connect", "batch_delete_schematic_wire"},
        "sch_components": {
            "get_schematic_component",
            "get_schematic_pin_locations",
            "list_schematic_components",
            "set_schematic_page",
            "update_symbols_from_library",
        },
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
        "batch_add_no_connect": ("sch_wiring", ("schematic", "positions"), ("schematic", "positions")),
        "get_schematic_pin_locations": ("sch_components", ("schematic", "reference"), ("schematic", "reference")),
        "set_schematic_page": ("sch_components", ("schematic", "size"), ("schematic", "size", "portrait")),
        "batch_place_components": ("sch_batch", ("schematic", "components"), ("schematic", "components")),
        "batch_edit_schematic_components": ("sch_batch", ("schematic", "edits"), ("schematic", "edits")),
        "batch_connect_to_net": ("sch_batch", ("schematic", "net_name", "pins"), ("schematic", "net_name", "pins")),
        "update_symbols_from_library": (
            "sch_components",
            ("schematic",),
            ("schematic", "dry_run", "allow_pin_moves", "references"),
        ),
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


def _pin_location(pin: dict[str, object]) -> tuple[str, float, float]:
    number = str(pin.get("pin_number", pin.get("number", "")))
    try:
        x = float(pin["x"])
        y = float(pin["y"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"pin {number or '?'} has invalid coordinates") from error
    if not math.isfinite(x) or not math.isfinite(y):
        raise RuntimeError(f"pin {number or '?'} has non-finite coordinates")
    return number, x, y


def _resolve_no_connect_positions(
    client: McpClient,
    schematic: Path,
    no_connects: tuple[NoConnectPin, ...],
) -> list[dict[str, float]]:
    by_reference: dict[str, set[str]] = defaultdict(set)
    for no_connect in no_connects:
        by_reference[no_connect.reference].add(no_connect.pin_number)
    positions: list[dict[str, float]] = []
    for reference, required_pins in by_reference.items():
        result = _call_tool_json(
            client,
            "get_schematic_pin_locations",
            {"schematic": str(schematic), "reference": reference},
        )
        pins = result.get("pins", [])
        if not isinstance(pins, list):
            raise RuntimeError("get_schematic_pin_locations returned non-list pins")
        located: dict[str, list[dict[str, float]]] = {pin: [] for pin in required_pins}
        for pin in pins:
            if not isinstance(pin, dict):
                raise RuntimeError(f"get_schematic_pin_locations returned invalid pin: {pin!r}")
            number, x, y = _pin_location(pin)
            if number in located:
                located[number].append({"x": x, "y": y})
        for pin_number in sorted(required_pins, key=int):
            matches = located[pin_number]
            if len(matches) != 1:
                raise RuntimeError(
                    f"expected exactly one {reference}.{pin_number} pin location, got {len(matches)}"
                )
            positions.append(matches[0])
    return positions


def _add_no_connects(
    client: McpClient,
    schematic: Path,
    no_connects: tuple[NoConnectPin, ...],
) -> None:
    if not no_connects:
        return
    positions = _resolve_no_connect_positions(client, schematic, no_connects)
    result = _call_tool_json(
        client,
        "batch_add_no_connect",
        {"schematic": str(schematic), "positions": positions},
    )
    if result.get("isError"):
        raise RuntimeError(f"batch_add_no_connect failed: {result}")


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
    _verify_final_symbol_refresh(client, schematic)
    _add_no_connects(client, schematic, plan.no_connects)
    for net_name, pins in _connections_by_net(plan.connections).items():
        client.call_tool(
            "batch_connect_to_net",
            {
                "schematic": str(schematic),
                "net_name": net_name,
                "pins": pins,
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
