from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from tools.lh60_design.mcp import McpClient
from tools.lh60_design.project import BOARD_HEIGHT_MM, BOARD_WIDTH_MM


ROOT = Path(__file__).resolve().parents[1]
SCHEMATIC = ROOT / "lh60.kicad_sch"
BOARD = ROOT / "lh60.kicad_pcb"
SCHEMA_VERSION = 1
BASELINE_REPORT_RELATIVE = "docs/reports/2026-08-18-debug-connectors-baseline.json"
EXPECTED_SCHEMATIC_HASH = "5322b7f21c10854aef14f7ca92ac35353f9fb9b7abd215451b4b4678a41aa1ac"
EXPECTED_BOARD_HASH = "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664"

TP_NETS = {
    "TP1": "VSYS",
    "TP2": "3V3",
    "TP3": "GND",
    "TP4": "COL0",
    "TP5": "COL1",
    "TP6": "COL2",
    "TP7": "COL3",
    "TP8": "COL4",
    "TP9": "COL5",
    "TP10": "COL6",
    "TP11": "COL7",
    "TP12": "COL8",
    "TP13": "COL9",
    "TP14": "ROW0",
    "TP15": "ROW1",
    "TP16": "ROW2",
    "TP17": "ROW3",
    "TP18": "ROW4",
    "TP19": "ROW5",
    "TP20": "ROW6",
    "TP21": "GP27",
    "TP22": "GP28",
    "TP23": "GP29",
}
CONNECTOR_PAD_NETS = {
    "J1": {"1": "VSYS", "2": "3V3", "3": "GND"},
    "J2": {"1": "COL0", "2": "COL1", "3": "COL2", "4": "COL3", "5": "COL4"},
    "J3": {"1": "COL5", "2": "COL6", "3": "COL7", "4": "COL8", "5": "COL9"},
    "J4": {"1": "ROW0", "2": "ROW1", "3": "ROW2", "4": "ROW3"},
    "J5": {"1": "ROW4", "2": "ROW5", "3": "ROW6"},
    "J6": {"1": "GP27", "2": "GP28", "3": "GP29"},
}
CONNECTOR_VALUES = {
    "J1": "PWR",
    "J2": "COL_A",
    "J3": "COL_B",
    "J4": "ROW_A",
    "J5": "ROW_B",
    "J6": "AUX",
}
CONNECTOR_FOOTPRINTS = {
    "J1": "lh60-core:PinHeader_1x03_P2.54mm_Vertical",
    "J2": "lh60-core:PinHeader_1x05_P2.54mm_Vertical",
    "J3": "lh60-core:PinHeader_1x05_P2.54mm_Vertical",
    "J4": "lh60-core:PinHeader_1x04_P2.54mm_Vertical",
    "J5": "lh60-core:PinHeader_1x03_P2.54mm_Vertical",
    "J6": "lh60-core:PinHeader_1x03_P2.54mm_Vertical",
}
SHARED_REFS = frozenset(
    {"U1"}
    | {f"D{index}" for index in range(1, 71)}
    | {f"SW{index}" for index in range(1, 59)}
    | {f"SW{index}" for index in range(60, 77)}
)
REBIND_REFS = tuple(sorted(SHARED_REFS))
TP_REFS = tuple(f"TP{index}" for index in range(1, 24))
OLD_BOARD_REFS = frozenset(SHARED_REFS | set(TP_REFS))
FINAL_BOARD_REFS = frozenset(SHARED_REFS | {f"J{index}" for index in range(1, 7)})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return (
        subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
        )
        .strip()
    )


def _git_parent_and_changed_paths() -> tuple[str, list[str]]:
    parent = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^"], text=True
    ).strip()
    changed = subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT),
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "HEAD",
        ],
        text=True,
    ).splitlines()
    return parent, sorted(path for path in changed if path)


def _require_baseline_git_revision(baseline_sha: str) -> None:
    current = _git_sha()
    if baseline_sha == current:
        return
    parent, changed_paths = _git_parent_and_changed_paths()
    if baseline_sha == parent and changed_paths == [BASELINE_REPORT_RELATIVE]:
        return
    raise RuntimeError(
        "baseline git_sha mismatch: expected current HEAD or its exact report-only parent"
    )


def _finite_number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise RuntimeError(f"{label} must be a finite number")
    return float(value)


def _require_exact_int(value: Any, expected: int, label: str) -> int:
    if type(value) is not int or value != expected:
        raise RuntimeError(f"{label} mismatch: expected {expected}, got {value}")
    return value


def _logical_net_name(board_net: Any, label: str) -> str:
    if not isinstance(board_net, str) or not board_net:
        raise RuntimeError(f"{label} board net must be a nonempty string")
    logical = board_net[1:] if board_net.startswith("/") else board_net
    if not logical or "/" in logical:
        raise RuntimeError(f"{label} board net has an unexpected hierarchical name: {board_net}")
    return logical


def _validate_hashes(schematic: Path, board: Path) -> tuple[str, str]:
    schematic_hash = _sha256(schematic)
    board_hash = _sha256(board)
    if schematic_hash != EXPECTED_SCHEMATIC_HASH:
        raise RuntimeError(f"protected schematic hash mismatch: {schematic_hash}")
    if board_hash != EXPECTED_BOARD_HASH:
        raise RuntimeError(f"protected PCB hash mismatch: {board_hash}")
    return schematic_hash, board_hash


def _require_contract(
    schemas: dict[str, dict[str, Any]],
    tool: str,
    required_inputs: tuple[str, ...],
    properties: tuple[str, ...],
) -> None:
    schema = schemas.get(tool)
    if schema is None:
        raise RuntimeError(f"Konnect PCB sync capability mismatch: missing {tool}")
    actual_required = schema.get("required")
    if not isinstance(actual_required, list) or set(actual_required) != set(required_inputs):
        raise RuntimeError(
            f"Konnect PCB sync capability mismatch: {tool} required inputs differ: "
            f"expected={sorted(required_inputs)}, actual={actual_required}"
        )
    missing = sorted(set(properties) - set(schema.get("properties", {})))
    if missing:
        raise RuntimeError(f"Konnect PCB sync capability mismatch: {tool} missing {missing}")


def require_pcb_sync_capabilities(client: McpClient) -> None:
    contracts = {
        "pcb_components": {
            "get_component_list": (("board",), ("board",)),
            "get_component_pads": (("board", "reference"), ("board", "reference")),
            "delete_component": (("board", "reference"), ("board", "reference")),
        },
        "pcb_board": {
            "get_board_info": (("board",), ("board",)),
        },
        "pcb_routing": {
            "query_traces": (("board",), ("board", "net_name")),
        },
        "sch_export": {
            "rebind_pcb_schematic_identities": (
                ("schematic", "board", "references"),
                ("schematic", "board", "references", "dry_run", "expected_plan_revision"),
            ),
            "update_pcb_from_schematic": (
                ("schematic", "board"),
                ("schematic", "board", "dry_run", "expected_plan_revision"),
            ),
        },
        "manufacturing": {
            "validate_for_manufacturing": (("board",), ("board",)),
        },
        "verification": {
            "run_drc": (("board",), ("board", "limit", "severity")),
        },
        "project": {
            "save_project": ((), ()),
        },
    }
    for toolset, tool_contracts in contracts.items():
        load_result = client.call_tool_json("load_toolset", {"name": toolset})
        if load_result.get("loaded") != toolset:
            raise RuntimeError(
                f"Konnect PCB sync capability mismatch: failed to load {toolset}"
            )
        owned_names = {
            item.get("name")
            for item in load_result.get("tools", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        missing_owned = sorted(set(tool_contracts) - owned_names)
        if missing_owned:
            raise RuntimeError(
                f"Konnect PCB sync capability mismatch: {toolset} does not own "
                f"{missing_owned}"
            )
        listed = client.request("tools/list", {}).get("tools")
        if not isinstance(listed, list):
            raise RuntimeError("Konnect PCB sync capability mismatch: tools/list malformed")
        schemas = {
            tool["name"]: tool.get("inputSchema", {})
            for tool in listed
            if isinstance(tool, dict) and tool.get("name") in owned_names
        }
        for tool, (required_inputs, properties) in tool_contracts.items():
            _require_contract(schemas, tool, required_inputs, properties)


def _component_inventory(client: McpClient, board: Path) -> dict[str, Any]:
    result = client.call_tool_json("get_component_list", {"board": str(board.resolve())})
    components = result.get("components")
    if not isinstance(components, list):
        raise RuntimeError("get_component_list returned no components list")
    _require_exact_int(
        result.get("count"), len(components), "get_component_list component count"
    )
    normalized = []
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("reference"), str):
            raise RuntimeError("component list entry is missing reference")
        reference = component["reference"]
        for field in ("value", "footprint", "layer"):
            if not isinstance(component.get(field), str):
                raise RuntimeError(f"{reference} component {field} is missing")
        normalized.append(
            {
                "reference": reference,
                "value": component["value"],
                "footprint": component["footprint"],
                "x": _finite_number(component.get("x"), f"{reference} component x"),
                "y": _finite_number(component.get("y"), f"{reference} component y"),
                "rotation": _finite_number(
                    component.get("rotation"), f"{reference} component rotation"
                ),
                "layer": component["layer"],
            }
        )
    references = [component["reference"] for component in normalized]
    duplicates = sorted(
        reference for reference in set(references) if references.count(reference) > 1
    )
    if duplicates:
        raise RuntimeError(f"get_component_list duplicate references: {duplicates}")
    normalized.sort(key=lambda component: component["reference"])
    return {
        "count": len(normalized),
        "references": sorted(references),
        "items": normalized,
    }


def _require_exact_inventory(
    client: McpClient,
    board: Path,
    expected: frozenset[str] | set[str],
    label: str,
) -> dict[str, Any]:
    inventory = _component_inventory(client, board)
    references = inventory["references"]
    actual = set(references)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise RuntimeError(f"{label} references mismatch: missing={missing}, extra={extra}")
    if len(references) != len(expected):
        raise RuntimeError(
            f"{label} reference count mismatch: expected={len(expected)}, actual={len(references)}"
        )
    return inventory


def _require_exact_references(
    client: McpClient,
    board: Path,
    expected: frozenset[str] | set[str],
    label: str,
) -> list[str]:
    return _require_exact_inventory(client, board, expected, label)["references"]


def _require_zone_count(client: McpClient, board: Path, expected: int) -> dict[str, Any]:
    result = client.call_tool_json("get_board_info", {"board": str(board.resolve())})
    _require_exact_int(result.get("zone_count"), expected, "zone_count")
    return result


def _require_manufacturing_track_count(
    client: McpClient,
    board: Path,
    expected: int,
) -> dict[str, Any]:
    result = client.call_tool_json("validate_for_manufacturing", {"board": str(board.resolve())})
    board_info = result.get("board_info")
    if not isinstance(board_info, dict):
        raise RuntimeError("validate_for_manufacturing returned no board_info")
    _require_exact_int(
        board_info.get("track_count"), expected, "manufacturing track_count"
    )
    if result.get("drc") is None:
        raise RuntimeError("validate_for_manufacturing returned null DRC")
    return result


def _require_tp_pads(client: McpClient, board: Path) -> dict[str, dict[str, Any]]:
    pads_by_reference = {}
    for reference in TP_REFS:
        result = client.call_tool_json(
            "get_component_pads",
            {"board": str(board.resolve()), "reference": reference},
        )
        pads = result.get("pads")
        if not isinstance(pads, list) or len(pads) != 1:
            raise RuntimeError(f"{reference} must have exactly one pad")
        if result.get("reference") != reference:
            raise RuntimeError(f"{reference} pad response identity/count mismatch")
        _require_exact_int(result.get("pad_count"), 1, f"{reference} pad_count")
        pad = pads[0]
        if not isinstance(pad, dict):
            raise RuntimeError(f"{reference} pad payload is invalid")
        if pad.get("number") != "1":
            raise RuntimeError(f"{reference} must expose pad 1")
        board_net = pad.get("net")
        logical_net = _logical_net_name(board_net, f"{reference} pad")
        if logical_net != TP_NETS[reference]:
            raise RuntimeError(f"{reference} net mismatch: expected {TP_NETS[reference]}")
        pads_by_reference[reference] = {
            "number": "1",
            "net": logical_net,
            "board_net": board_net,
            "x": _finite_number(pad.get("x"), f"{reference} pad x"),
            "y": _finite_number(pad.get("y"), f"{reference} pad y"),
        }
    return pads_by_reference


def _require_empty_traces(
    client: McpClient,
    board: Path,
    expected_references: frozenset[str] | set[str],
    label: str,
    board_nets: dict[str, str],
) -> dict[str, dict[str, Any]]:
    # query_traces currently ignores its board argument and uses the active IPC
    # board.  Bind the following batch to the intended live board immediately
    # before querying any net.
    _require_exact_references(client, board, expected_references, label)
    traces = {}
    if set(board_nets) != set(TP_NETS.values()):
        raise RuntimeError("board-net trace map does not cover the frozen debug nets")
    for net_name in TP_NETS.values():
        board_net = board_nets[net_name]
        result = client.call_tool_json(
            "query_traces",
            {"board": str(board.resolve()), "net_name": board_net},
        )
        try:
            _require_exact_int(result.get("count"), 0, f"{net_name} trace count")
        except RuntimeError as error:
            raise RuntimeError(f"{net_name} must have zero board traces") from error
        if result.get("traces") != []:
            raise RuntimeError(f"{net_name} must have zero board traces")
        traces[net_name] = {"board_net": board_net, **result}
    return traces


def _require_complete_drc(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError("DRC evidence must be a complete nonempty object")
    required = {
        "total_violations",
        "design_rule_violations",
        "unconnected_items",
        "schematic_parity",
        "categories_not_reported",
        "filtered_count",
        "errors",
        "warnings",
        "severity_filter",
        "shown",
        "truncated",
        "violations",
    }
    if required - set(payload):
        raise RuntimeError("DRC evidence is not complete")
    if payload["severity_filter"] != "info":
        raise RuntimeError("DRC evidence is not complete at info severity")
    if payload["categories_not_reported"] != [] or payload["truncated"] is not False:
        raise RuntimeError("DRC evidence is not complete")
    numeric_fields = (
        "total_violations",
        "design_rule_violations",
        "unconnected_items",
        "schematic_parity",
        "filtered_count",
        "errors",
        "warnings",
        "shown",
    )
    if any(
        type(payload[field]) is not int or payload[field] < 0
        for field in numeric_fields
    ):
        raise RuntimeError("DRC evidence is not complete")
    if (
        payload["filtered_count"] != payload["total_violations"]
        or payload["shown"] != payload["filtered_count"]
        or not isinstance(payload["violations"], list)
        or len(payload["violations"]) != payload["shown"]
    ):
        raise RuntimeError("DRC evidence is not complete")
    return payload


def _centroid(pads: dict[str, dict[str, Any]], references: tuple[str, ...]) -> dict[str, float]:
    return {
        "x": sum(pads[reference]["x"] for reference in references) / len(references),
        "y": sum(pads[reference]["y"] for reference in references) / len(references),
    }


def _expected_centroids(pads: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    return {
        "J1": _centroid(pads, ("TP1", "TP2", "TP3")),
        "J2": _centroid(pads, ("TP4", "TP5", "TP6", "TP7", "TP8")),
        "J3": _centroid(pads, ("TP9", "TP10", "TP11", "TP12", "TP13")),
        "J4": _centroid(pads, ("TP14", "TP15", "TP16", "TP17")),
        "J5": _centroid(pads, ("TP18", "TP19", "TP20")),
        "J6": _centroid(pads, ("TP21", "TP22", "TP23")),
    }


def _board_nets_from_pads(pads: dict[str, dict[str, Any]]) -> dict[str, str]:
    board_nets: dict[str, str] = {}
    for pad in pads.values():
        logical_net = pad["net"]
        board_net = pad["board_net"]
        if logical_net in board_nets and board_nets[logical_net] != board_net:
            raise RuntimeError(f"debug net {logical_net} has inconsistent board net names")
        board_nets[logical_net] = board_net
    return board_nets


def capture_baseline(client: McpClient, schematic: Path, board: Path) -> dict[str, Any]:
    require_pcb_sync_capabilities(client)
    schematic_hash, board_hash = _validate_hashes(schematic, board)
    inventory = _require_exact_inventory(client, board, OLD_BOARD_REFS, "baseline 169")
    board_info = _require_zone_count(client, board, 0)
    manufacturing = _require_manufacturing_track_count(client, board, 0)
    tp_pads = _require_tp_pads(client, board)
    traces = _require_empty_traces(
        client,
        board,
        OLD_BOARD_REFS,
        "baseline trace binding 169",
        _board_nets_from_pads(tp_pads),
    )
    drc = _require_complete_drc(
        client.call_tool_json(
            "run_drc",
            {"board": str(board.resolve()), "limit": 10000, "severity": "info"},
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "git_sha": _git_sha(),
        "schematic": str(schematic.resolve()),
        "board": str(board.resolve()),
        "schematic_hash": schematic_hash,
        "board_hash": board_hash,
        "components": inventory,
        "tp_nets": deepcopy(TP_NETS),
        "connector_pad_nets": deepcopy(CONNECTOR_PAD_NETS),
        "connector_values": deepcopy(CONNECTOR_VALUES),
        "connector_footprints": deepcopy(CONNECTOR_FOOTPRINTS),
        "tp_pads": tp_pads,
        "centroids": _expected_centroids(tp_pads),
        "board_info": board_info,
        "manufacturing": manufacturing,
        "traces": traces,
        "drc": drc,
    }


def _require_baseline_shape(baseline: dict[str, Any], schematic: Path, board: Path) -> None:
    if baseline.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("baseline schema_version mismatch")
    if baseline.get("schematic") != str(schematic.resolve()):
        raise RuntimeError("baseline schematic path mismatch")
    if baseline.get("board") != str(board.resolve()):
        raise RuntimeError("baseline board path mismatch")
    if baseline.get("tp_nets") != TP_NETS:
        raise RuntimeError("baseline tp_nets mismatch")
    if baseline.get("connector_pad_nets") != CONNECTOR_PAD_NETS:
        raise RuntimeError("baseline connector_pad_nets mismatch")
    git_sha = baseline.get("git_sha")
    if (
        not isinstance(git_sha, str)
        or len(git_sha) != 40
        or any(character not in "0123456789abcdef" for character in git_sha)
    ):
        raise RuntimeError("baseline git_sha mismatch")
    if baseline.get("connector_values") != CONNECTOR_VALUES:
        raise RuntimeError("baseline connector_values mismatch")
    if baseline.get("connector_footprints") != CONNECTOR_FOOTPRINTS:
        raise RuntimeError("baseline connector_footprints mismatch")
    components = baseline.get("components")
    if not isinstance(components, dict):
        raise RuntimeError("baseline components payload mismatch")
    references = components.get("references")
    if set(references or []) != OLD_BOARD_REFS:
        raise RuntimeError("baseline component inventory mismatch")
    if components.get("count") != len(OLD_BOARD_REFS):
        raise RuntimeError("baseline component count mismatch")
    items = components.get("items")
    if not isinstance(items, list) or len(items) != len(OLD_BOARD_REFS):
        raise RuntimeError("baseline component items mismatch")
    tp_pads = baseline.get("tp_pads")
    if not isinstance(tp_pads, dict) or set(tp_pads) != set(TP_NETS):
        raise RuntimeError("baseline tp_pads mismatch")
    for reference, expected_net in TP_NETS.items():
        pad = tp_pads.get(reference)
        if not isinstance(pad, dict) or pad.get("number") != "1" or pad.get("net") != expected_net:
            raise RuntimeError(f"baseline tp_pads mismatch for {reference}")
        if _logical_net_name(pad.get("board_net"), f"baseline tp_pads {reference}") != expected_net:
            raise RuntimeError(f"baseline tp_pads mismatch for {reference}")
        _finite_number(pad.get("x"), f"baseline tp_pads {reference} x")
        _finite_number(pad.get("y"), f"baseline tp_pads {reference} y")
    if baseline.get("centroids") != _expected_centroids(tp_pads):
        raise RuntimeError("baseline centroids mismatch")
    board_info = baseline.get("board_info")
    if not isinstance(board_info, dict):
        raise RuntimeError("baseline board_info mismatch")
    _require_exact_int(board_info.get("zone_count"), 0, "baseline board_info zone_count")
    manufacturing = baseline.get("manufacturing")
    if not isinstance(manufacturing, dict) or not isinstance(manufacturing.get("board_info"), dict):
        raise RuntimeError("baseline manufacturing mismatch")
    _require_exact_int(
        manufacturing["board_info"].get("track_count"), 0, "baseline manufacturing track_count"
    )
    if manufacturing.get("drc") is None:
        raise RuntimeError("baseline manufacturing DRC mismatch")
    traces = baseline.get("traces")
    if not isinstance(traces, dict) or set(traces) != set(TP_NETS.values()):
        raise RuntimeError("baseline traces mismatch")
    for net_name, trace in traces.items():
        if not isinstance(trace, dict) or trace.get("traces") != []:
            raise RuntimeError(f"baseline traces mismatch for {net_name}")
        _require_exact_int(trace.get("count"), 0, f"baseline traces {net_name} count")
        if trace.get("board_net") != _board_nets_from_pads(tp_pads)[net_name]:
            raise RuntimeError(f"baseline traces mismatch for {net_name}")
    try:
        _require_complete_drc(baseline.get("drc"))
    except RuntimeError as error:
        raise RuntimeError("baseline drc mismatch") from error


def _validate_change(change: dict[str, Any], reference: str) -> None:
    if change.get("kind") != "add":
        raise RuntimeError("only add changes are allowed")
    if change.get("reference") != reference:
        raise RuntimeError(f"unexpected change reference: {change.get('reference')}")
    if change.get("value") != CONNECTOR_VALUES[reference]:
        raise RuntimeError(f"{reference} value mismatch")
    if change.get("footprint_id") != CONNECTOR_FOOTPRINTS[reference]:
        raise RuntimeError(f"{reference} footprint mismatch")
    if not isinstance(change.get("symbol_path"), str) or not change["symbol_path"]:
        raise RuntimeError(f"{reference} symbol_path must be nonempty")
    if change.get("dnp") is not False:
        raise RuntimeError(f"{reference} dnp must be false")
    pad_nets = change.get("pad_nets")
    if not isinstance(pad_nets, dict) or set(pad_nets) != set(CONNECTOR_PAD_NETS[reference]):
        raise RuntimeError(f"{reference} pad_nets mismatch")
    normalized_pad_nets = {
        number: _logical_net_name(pad_nets[number], f"{reference} pad {number}")
        for number in sorted(CONNECTOR_PAD_NETS[reference])
    }
    if normalized_pad_nets != CONNECTOR_PAD_NETS[reference]:
        raise RuntimeError(f"{reference} pad_nets mismatch")
    position = change.get("position")
    if not isinstance(position, dict):
        raise RuntimeError(f"{reference} position payload is invalid")
    _finite_number(position.get("x"), f"{reference} position x")
    _finite_number(position.get("y"), f"{reference} position y")


def _validate_sync_plan(
    payload: dict[str, Any],
    *,
    expected_status: str,
    expected_board_only: int,
    expected_board_only_applied: int,
    expected_added_applied: int,
    expected_skipped_applied: int,
    require_undo: bool,
) -> dict[str, Any]:
    if payload.get("status") != expected_status:
        raise RuntimeError(f"sync status mismatch: expected {expected_status}")
    if not isinstance(payload.get("plan_revision"), str) or not payload["plan_revision"]:
        raise RuntimeError("sync plan_revision must be nonempty")
    diagnostics = payload.get("diagnostics")
    if diagnostics != []:
        raise RuntimeError(f"sync diagnostic mismatch: {diagnostics}")
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise RuntimeError("sync coverage is missing")
    expected_metadata = {
        "source": "saved_schematic_hierarchy",
        "transport": "live_kicad_ipc",
        "atomicity": "single_kicad_undo_commit",
    }
    if any(coverage.get(field) != value for field, value in expected_metadata.items()):
        raise RuntimeError("sync coverage metadata mismatch")
    if type(coverage.get("hierarchy_files")) is not int or coverage["hierarchy_files"] < 1:
        raise RuntimeError("sync coverage metadata mismatch")
    expected_counts = {
        "footprints_added": (6 if expected_status != "noop" else 0, expected_added_applied),
        "footprints_updated": (0, 0),
        "pads_reassigned": (0, 0),
        "board_only_preserved": (expected_board_only, expected_board_only_applied),
        "skipped_by_flag": (3, expected_skipped_applied),
        "conflicts": (0, 0),
    }
    for field, (planned, applied) in expected_counts.items():
        pair = coverage.get(field)
        if not isinstance(pair, dict):
            raise RuntimeError(f"{field} mismatch: {pair}")
        if (
            type(pair.get("planned")) is not int
            or type(pair.get("applied")) is not int
            or pair != {"planned": planned, "applied": applied}
        ):
            raise RuntimeError(f"{field} mismatch: {pair}")
    changes = payload.get("changes")
    if expected_status == "noop":
        if changes != []:
            raise RuntimeError("noop must not report changes")
    else:
        if not isinstance(changes, list) or len(changes) != 6:
            raise RuntimeError("sync must report exactly six add changes")
        by_reference = {change.get("reference"): change for change in changes}
        if set(by_reference) != set(CONNECTOR_PAD_NETS):
            raise RuntimeError(f"sync change references mismatch: {sorted(by_reference)}")
        for reference in sorted(CONNECTOR_PAD_NETS):
            _validate_change(by_reference[reference], reference)
    undo = payload.get("undo")
    if require_undo and (not isinstance(undo, str) or not undo.strip()):
        raise RuntimeError("apply result must include undo guidance")
    if not require_undo and undo is not None:
        raise RuntimeError("dry-run/noop result must not include undo guidance")
    return payload


def _rebind_component_contracts() -> dict[str, dict[str, Any]]:
    from tools.lh60_design.schematic import build_schematic_plan

    plan = build_schematic_plan()
    components = {component.reference: component for component in plan.components}
    pad_nets = {reference: {} for reference in REBIND_REFS}
    for connection in plan.connections:
        if connection.reference in pad_nets:
            pad_nets[connection.reference][connection.pin_number] = connection.net_name
    return {
        reference: {
            "value": components[reference].value,
            "footprint_id": components[reference].footprint,
            "dnp": components[reference].dnp is True,
            "pad_nets": dict(sorted(pad_nets[reference].items())),
        }
        for reference in REBIND_REFS
    }


def _require_symbol_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value == "/":
        raise RuntimeError(f"{label} must be a nonempty symbol path")
    segments = value.split("/")[1:] if value.startswith("/") else []
    if not segments or any(not segment for segment in segments):
        raise RuntimeError(f"{label} must be a valid symbol path")
    try:
        for segment in segments:
            uuid.UUID(segment)
    except (ValueError, AttributeError) as error:
        raise RuntimeError(f"{label} must be a valid symbol path") from error
    return value


def _validate_rebind_change(
    change: Any, reference: str, contracts: dict[str, dict[str, Any]]
) -> None:
    if not isinstance(change, dict):
        raise RuntimeError(f"{reference} rebind change must be an object")
    expected_fields = {
        "reference", "kiid", "old_symbol_path", "new_symbol_path", "value",
        "footprint_id", "dnp", "pad_nets", "preserve",
    }
    if set(change) != expected_fields:
        raise RuntimeError(f"{reference} rebind change fields mismatch")
    if change["reference"] != reference:
        raise RuntimeError(f"unexpected rebind change reference: {change['reference']}")
    if not isinstance(change["kiid"], str) or not change["kiid"]:
        raise RuntimeError(f"{reference} kiid must be nonempty")
    try:
        uuid.UUID(change["kiid"])
    except (ValueError, AttributeError) as error:
        raise RuntimeError(f"{reference} kiid must be a UUID") from error
    old_path = _require_symbol_path(change["old_symbol_path"], f"{reference} old_symbol_path")
    new_path = _require_symbol_path(change["new_symbol_path"], f"{reference} new_symbol_path")
    if old_path == new_path:
        raise RuntimeError(f"{reference} rebind symbol paths must differ")
    contract = contracts[reference]
    for field in ("value", "footprint_id", "dnp", "pad_nets"):
        if change[field] != contract[field]:
            raise RuntimeError(f"{reference} rebind {field} mismatch")
    preserve = change["preserve"]
    if not isinstance(preserve, dict) or set(preserve) != {"position", "rotation", "layer", "locked"}:
        raise RuntimeError(f"{reference} rebind preserve shape mismatch")
    position = preserve["position"]
    if not isinstance(position, dict) or set(position) != {"x", "y"}:
        raise RuntimeError(f"{reference} rebind preserve position mismatch")
    _finite_number(position["x"], f"{reference} rebind preserve x")
    _finite_number(position["y"], f"{reference} rebind preserve y")
    _finite_number(preserve["rotation"], f"{reference} rebind preserve rotation")
    if not isinstance(preserve["layer"], str) or not preserve["layer"]:
        raise RuntimeError(f"{reference} rebind preserve layer mismatch")
    if type(preserve["locked"]) is not bool:
        raise RuntimeError(f"{reference} rebind preserve locked mismatch")


def _validate_rebind_plan(
    payload: dict[str, Any],
    *,
    expected_status: str,
    expected_planned: int,
    expected_applied: int,
    require_undo: bool,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {
        "status", "plan_revision", "coverage", "changes", "diagnostics", "undo",
    }:
        raise RuntimeError("rebind plan fields mismatch")
    if payload["status"] != expected_status:
        raise RuntimeError(f"rebind status mismatch: expected {expected_status}")
    if not isinstance(payload["plan_revision"], str) or not payload["plan_revision"]:
        raise RuntimeError("rebind plan_revision must be nonempty")
    if payload["diagnostics"] != []:
        raise RuntimeError(f"rebind diagnostic mismatch: {payload['diagnostics']}")
    coverage = payload["coverage"]
    expected_coverage = {
        "source": "saved_schematic_hierarchy",
        "transport": "live_kicad_ipc",
        "atomicity": "single_kicad_undo_commit",
        "requested": len(REBIND_REFS),
        "eligible": 0 if expected_status == "noop" else len(REBIND_REFS),
        "planned": expected_planned,
        "applied": expected_applied,
        "conflicts": 0,
    }
    if not isinstance(coverage, dict) or set(coverage) != {
        *expected_coverage, "hierarchy_files",
    }:
        raise RuntimeError("rebind coverage fields mismatch")
    if type(coverage["hierarchy_files"]) is not int or coverage["hierarchy_files"] < 1:
        raise RuntimeError("rebind hierarchy_files mismatch")
    for field, expected in expected_coverage.items():
        if type(coverage[field]) is not type(expected) or coverage[field] != expected:
            raise RuntimeError(f"rebind coverage {field} mismatch")
    changes = payload["changes"]
    if expected_status == "noop":
        if changes != []:
            raise RuntimeError("rebind noop must not report changes")
    else:
        if not isinstance(changes, list) or len(changes) != len(REBIND_REFS):
            raise RuntimeError("rebind must report exactly 146 changes")
        by_reference = {change.get("reference"): change for change in changes if isinstance(change, dict)}
        if len(by_reference) != len(changes) or tuple(sorted(by_reference)) != REBIND_REFS:
            raise RuntimeError("rebind change references mismatch")
        if tuple(change["reference"] for change in changes) != REBIND_REFS:
            raise RuntimeError("rebind change order mismatch")
        contracts = _rebind_component_contracts()
        for reference in REBIND_REFS:
            _validate_rebind_change(by_reference[reference], reference, contracts)
    undo = payload["undo"]
    if require_undo and (not isinstance(undo, str) or not undo.strip()):
        raise RuntimeError("rebind apply result must include undo guidance")
    if not require_undo and undo is not None:
        raise RuntimeError("rebind dry-run/noop result must not include undo guidance")
    return payload


def _require_connector_pads(client: McpClient, board: Path) -> dict[str, Any]:
    connector_pads = {}
    for reference in sorted(CONNECTOR_PAD_NETS):
        result = client.call_tool_json(
            "get_component_pads",
            {"board": str(board.resolve()), "reference": reference},
        )
        pads = result.get("pads")
        if not isinstance(pads, list) or len(pads) != len(CONNECTOR_PAD_NETS[reference]):
            raise RuntimeError(f"{reference} pad count mismatch")
        if result.get("reference") != reference:
            raise RuntimeError(f"{reference} pad response identity/count mismatch")
        _require_exact_int(
            result.get("pad_count"),
            len(CONNECTOR_PAD_NETS[reference]),
            f"{reference} pad_count",
        )
        actual = {}
        normalized_pads = []
        for pad in pads:
            if not isinstance(pad, dict):
                raise RuntimeError(f"{reference} pad payload is invalid")
            number = str(pad.get("number"))
            board_net = pad.get("net")
            logical_net = _logical_net_name(board_net, f"{reference} pad {number}")
            actual[number] = logical_net
            normalized_pads.append(
                {
                    "number": number,
                    "net": logical_net,
                    "board_net": board_net,
                    "x": _finite_number(pad.get("x"), f"{reference} pad x"),
                    "y": _finite_number(pad.get("y"), f"{reference} pad y"),
                }
            )
        if actual != CONNECTOR_PAD_NETS[reference]:
            raise RuntimeError(f"{reference} post-save pad-net mismatch")
        connector_pads[reference] = {
            "reference": reference,
            "pad_count": len(normalized_pads),
            "pads": sorted(normalized_pads, key=lambda pad: pad["number"]),
        }
    return connector_pads


def _require_connector_instances(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_reference = {component["reference"]: component for component in inventory["items"]}
    connectors = {}
    for reference in sorted(CONNECTOR_PAD_NETS):
        component = by_reference.get(reference)
        if not isinstance(component, dict):
            raise RuntimeError(f"{reference} connector readback is missing")
        if component.get("value") != CONNECTOR_VALUES[reference]:
            raise RuntimeError(f"{reference} value mismatch")
        if component.get("footprint") != CONNECTOR_FOOTPRINTS[reference]:
            raise RuntimeError(f"{reference} footprint mismatch")
        if component.get("layer") != "F.Cu":
            raise RuntimeError(f"{reference} layer mismatch: expected F.Cu")
        _finite_number(component.get("x"), f"{reference} readback x")
        _finite_number(component.get("y"), f"{reference} readback y")
        if 0.0 <= component["x"] <= BOARD_WIDTH_MM and 0.0 <= component["y"] <= BOARD_HEIGHT_MM:
            raise RuntimeError(f"{reference} staged connector must remain outside board bounds")
        connectors[reference] = component
    return connectors


def sync_debug_connectors(
    client: McpClient,
    schematic: Path,
    board: Path,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    require_pcb_sync_capabilities(client)
    _require_baseline_shape(baseline, schematic, board)
    _require_baseline_git_revision(baseline["git_sha"])
    schematic_hash, board_hash = _validate_hashes(schematic, board)
    if baseline.get("schematic_hash") != schematic_hash or baseline.get("board_hash") != board_hash:
        raise RuntimeError("baseline hash mismatch")

    before_inventory = _require_exact_inventory(client, board, OLD_BOARD_REFS, "pre-delete 169")
    if before_inventory != baseline["components"]:
        raise RuntimeError("live component inventory differs from captured baseline")
    before_refs = before_inventory["references"]
    before_board_info = _require_zone_count(client, board, 0)
    before_manufacturing = _require_manufacturing_track_count(client, board, 0)
    before_tp_pads = _require_tp_pads(client, board)
    if before_tp_pads != baseline["tp_pads"]:
        raise RuntimeError("live TP pad state differs from captured baseline")
    before_traces = _require_empty_traces(
        client,
        board,
        OLD_BOARD_REFS,
        "pre-delete trace binding 169",
        _board_nets_from_pads(before_tp_pads),
    )

    rebind_args = {
        "schematic": str(schematic.resolve()),
        "board": str(board.resolve()),
        "references": list(REBIND_REFS),
    }
    rebind_dry_run = _validate_rebind_plan(
        client.call_tool_json(
            "rebind_pcb_schematic_identities", {**rebind_args, "dry_run": True}
        ),
        expected_status="ready",
        expected_planned=len(REBIND_REFS),
        expected_applied=0,
        require_undo=False,
    )
    rebind_apply = _validate_rebind_plan(
        client.call_tool_json(
            "rebind_pcb_schematic_identities",
            {
                **rebind_args,
                "dry_run": False,
                "expected_plan_revision": rebind_dry_run["plan_revision"],
            },
        ),
        expected_status="applied",
        expected_planned=len(REBIND_REFS),
        expected_applied=len(REBIND_REFS),
        require_undo=True,
    )
    if rebind_apply["plan_revision"] != rebind_dry_run["plan_revision"]:
        raise RuntimeError("rebind apply result plan_revision differs from dry run")
    rebind_noop = _validate_rebind_plan(
        client.call_tool_json(
            "rebind_pcb_schematic_identities", {**rebind_args, "dry_run": True}
        ),
        expected_status="noop",
        expected_planned=0,
        expected_applied=0,
        require_undo=False,
    )
    post_rebind_inventory = _require_exact_inventory(
        client, board, OLD_BOARD_REFS, "post-rebind 169"
    )
    if post_rebind_inventory != before_inventory:
        raise RuntimeError("post-rebind component inventory differs from pre-rebind state")
    post_rebind_tp_pads = _require_tp_pads(client, board)
    if post_rebind_tp_pads != before_tp_pads:
        raise RuntimeError("post-rebind TP pad state differs from pre-rebind state")
    post_rebind_traces = _require_empty_traces(
        client,
        board,
        OLD_BOARD_REFS,
        "post-rebind trace binding 169",
        _board_nets_from_pads(post_rebind_tp_pads),
    )
    if post_rebind_traces != before_traces:
        raise RuntimeError("post-rebind trace state differs from pre-rebind state")

    first_dry = _validate_sync_plan(
        client.call_tool_json(
            "update_pcb_from_schematic",
            {"schematic": str(schematic.resolve()), "board": str(board.resolve()), "dry_run": True},
        ),
        expected_status="ready",
        expected_board_only=23,
        expected_board_only_applied=0,
        expected_added_applied=0,
        expected_skipped_applied=0,
        require_undo=False,
    )

    delete_results = []
    for reference in TP_REFS:
        result = client.call_tool_json(
            "delete_component",
            {"board": str(board.resolve()), "reference": reference},
        )
        if result.get("deleted") != reference:
            raise RuntimeError(f"delete response mismatch for {reference}")
        delete_results.append(result)

    _require_exact_references(client, board, SHARED_REFS, "post-delete 146")
    second_dry = _validate_sync_plan(
        client.call_tool_json(
            "update_pcb_from_schematic",
            {"schematic": str(schematic.resolve()), "board": str(board.resolve()), "dry_run": True},
        ),
        expected_status="ready",
        expected_board_only=0,
        expected_board_only_applied=0,
        expected_added_applied=0,
        expected_skipped_applied=0,
        require_undo=False,
    )
    if second_dry["plan_revision"] == first_dry["plan_revision"]:
        raise RuntimeError("second dry-run plan_revision must differ after TP deletion")
    apply_result = _validate_sync_plan(
        client.call_tool_json(
            "update_pcb_from_schematic",
            {
                "schematic": str(schematic.resolve()),
                "board": str(board.resolve()),
                "dry_run": False,
                "expected_plan_revision": second_dry["plan_revision"],
            },
        ),
        expected_status="applied",
        expected_board_only=0,
        expected_board_only_applied=0,
        expected_added_applied=6,
        expected_skipped_applied=3,
        require_undo=True,
    )
    if apply_result["plan_revision"] != second_dry["plan_revision"]:
        raise RuntimeError("apply result plan_revision differs from second dry run")

    pre_save_refs = _require_exact_references(client, board, FINAL_BOARD_REFS, "final 152")
    pre_save_connector_pads = _require_connector_pads(client, board)
    pre_save_traces = _require_empty_traces(
        client,
        board,
        FINAL_BOARD_REFS,
        "pre-save trace binding 152",
        {
            pad["net"]: pad["board_net"]
            for connector in pre_save_connector_pads.values()
            for pad in connector["pads"]
        },
    )
    pre_save_noop = _validate_sync_plan(
        client.call_tool_json(
            "update_pcb_from_schematic",
            {"schematic": str(schematic.resolve()), "board": str(board.resolve()), "dry_run": True},
        ),
        expected_status="noop",
        expected_board_only=0,
        expected_board_only_applied=0,
        expected_added_applied=0,
        expected_skipped_applied=0,
        require_undo=False,
    )
    client.call_tool("save_project", {})
    after_schematic_hash = _sha256(schematic)
    after_board_hash = _sha256(board)
    if after_schematic_hash != schematic_hash:
        raise RuntimeError("protected schematic changed during PCB synchronization")
    if after_board_hash == board_hash:
        raise RuntimeError("saved PCB hash did not change after connector synchronization")

    post_save_inventory = _require_exact_inventory(
        client, board, FINAL_BOARD_REFS, "post-save final 152"
    )
    post_save_refs = post_save_inventory["references"]
    post_save_connectors = _require_connector_instances(post_save_inventory)
    connector_pads = _require_connector_pads(client, board)
    post_save_board_info = _require_zone_count(client, board, 0)
    post_save_manufacturing = _require_manufacturing_track_count(client, board, 0)
    post_save_traces = _require_empty_traces(
        client,
        board,
        FINAL_BOARD_REFS,
        "post-save trace binding 152",
        {
            pad["net"]: pad["board_net"]
            for connector in connector_pads.values()
            for pad in connector["pads"]
        },
    )
    post_save_drc = _require_complete_drc(
        client.call_tool_json(
            "run_drc",
            {"board": str(board.resolve()), "limit": 10000, "severity": "info"},
        )
    )
    final_noop = _validate_sync_plan(
        client.call_tool_json(
            "update_pcb_from_schematic",
            {"schematic": str(schematic.resolve()), "board": str(board.resolve()), "dry_run": True},
        ),
        expected_status="noop",
        expected_board_only=0,
        expected_board_only_applied=0,
        expected_added_applied=0,
        expected_skipped_applied=0,
        require_undo=False,
    )
    return {
        "before_hashes": {"schematic": schematic_hash, "board": board_hash},
        "before": {
            "references": before_refs,
            "board_info": before_board_info,
            "manufacturing": before_manufacturing,
            "tp_pads": before_tp_pads,
            "traces": before_traces,
        },
        "rebind_dry_run": rebind_dry_run,
        "rebind_apply": rebind_apply,
        "rebind_noop": rebind_noop,
        "post_rebind": {
            "inventory": post_rebind_inventory,
            "tp_pads": post_rebind_tp_pads,
            "traces": post_rebind_traces,
        },
        "first_dry_run": first_dry,
        "delete_results": delete_results,
        "second_dry_run": second_dry,
        "apply": apply_result,
        "pre_save": {
            "references": pre_save_refs,
            "connector_pads": pre_save_connector_pads,
            "traces": pre_save_traces,
            "noop": pre_save_noop,
        },
        "post_save": {
            "references": post_save_refs,
            "connectors": post_save_connectors,
            "connector_pads": connector_pads,
            "board_info": post_save_board_info,
            "manufacturing": post_save_manufacturing,
            "traces": post_save_traces,
            "drc": post_save_drc,
        },
        "final_noop": final_noop,
        "after_hashes": {"schematic": after_schematic_hash, "board": after_board_hash},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guarded LH60 debug connector PCB sync helper.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture-baseline", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--schematic", type=Path, default=SCHEMATIC)
    parser.add_argument("--board", type=Path, default=BOARD)
    parser.add_argument("--konnect", type=Path, default=Path.home() / ".local/bin/konnect")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".config/konnect/config.toml",
    )
    args = parser.parse_args(argv)
    if args.apply and args.baseline is None:
        parser.error("--apply requires --baseline")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    with McpClient(args.konnect, args.config) as client:
        if args.capture_baseline:
            result = capture_baseline(client, args.schematic, args.board)
        else:
            baseline = json.loads(args.baseline.read_text())
            result = sync_debug_connectors(client, args.schematic, args.board, baseline)
    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    contents = json.dumps(result, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=report.parent,
        prefix=f".{report.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(contents)
        temporary.flush()
        temporary_path = Path(temporary.name)
    temporary_path.replace(report)


if __name__ == "__main__":
    main()
