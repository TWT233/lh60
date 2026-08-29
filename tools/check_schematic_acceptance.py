from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from tools.lh60_design.mcp import McpClient
from tools.lh60_design.schematic import (
    SCHEMATIC,
    apply_schematic,
    build_schematic_plan,
    require_schematic_capabilities,
)
from tools.lh60_design.core_library import apply_core_library
from tools.lh60_design.interconnect import interboard_contract
from tools.lh60_design.interconnect_library import (
    FOOTPRINT_LIBRARY as INTERCONNECT_FOOTPRINT_LIBRARY,
    FOOTPRINT_PATH as INTERCONNECT_FOOTPRINT_PATH,
    SYMBOL_LIBRARY as INTERCONNECT_SYMBOL_LIBRARY,
    SYMBOL_NAME as INTERCONNECT_SYMBOL_NAME,
    apply_interconnect_library,
)
from tools.lh60_design.core_library import FOOTPRINT_LIBRARY as CORE_FOOTPRINT_LIBRARY


ROOT = Path(__file__).resolve().parents[1]
KONNECT = Path("/data00/home/wangqiyilang/.local/bin/konnect")
CONFIG = Path.home() / ".config/konnect/config.toml"
BOARD = ROOT / "lh60.kicad_pcb"


CURRENT_ACCEPTANCE_BASELINE = {"component_count": 146, "wire_count": 0, "label_count": 313, "no_connect_count": 1}
EXPECTED_INVENTORY = {"switch": 75, "diode": 70, "connector": 1}
EXPECTED_PRODUCTION_REFERENCES = frozenset(
    {"J1"}
    | {f"D{index}" for index in range(1, 71)}
    | {f"SW{index}" for index in range(1, 77) if index != 59}
)
CURRENT_155_BASELINE = {"component_count": 155, "wire_count": 0, "label_count": 339}
CURRENT_155_REFERENCES = frozenset(
    {"U1", *{f"#FLG{index:02d}" for index in range(1, 4)}}
    | {f"D{index}" for index in range(1, 71)}
    | {f"SW{index}" for index in range(1, 77) if index != 59}
    | {f"J{index}" for index in range(1, 7)}
)
FROZEN_COMPONENT_SHA256 = ""
FROZEN_PIN_SHA256 = ""
FROZEN_CONNECTOR_MAP = {
    "J1": tuple(
        (str(pin.number), pin.net_name)
        for pin in interboard_contract().pins
        if pin.net_name is not None
    ),
}
PROHIBITED_NETS = interboard_contract().prohibited_nets | {"NC"}
VISUAL_CHECKLIST = {"j1_pin_order", "j1_nc_marker", "j1_fields", "matrix", "title_block"}
SOURCE_155_SCHEMATIC_SHA256 = "5322b7f21c10854aef14f7ca92ac35353f9fb9b7abd215451b4b4678a41aa1ac"
SOURCE_155_PCB_SHA256 = "eb27463ebcb973e44b5aea551c79ac4470615a3a7f0519a4b1c54c2afd466a46"


def _expected_migration_references() -> frozenset[str]:
    return frozenset(component.reference for component in build_schematic_plan().components)


def _plan_hash() -> str:
    plan = build_schematic_plan()
    payload = {
        "components": [component.__dict__ for component in plan.components],
        "connections": [connection.__dict__ for connection in plan.connections],
        "no_connects": [no_connect.__dict__ for no_connect in plan.no_connects],
        "page_size": plan.page_size,
        "portrait": plan.portrait,
        "field_visibility": [item.__dict__ for item in plan.field_visibility],
    }
    return hashlib.sha256(json.dumps(payload, default=list, sort_keys=True).encode()).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def assert_unique_nonempty_uuids(items: list[dict[str, Any]], item_name: str) -> list[str]:
    uuids = [str(item.get("uuid", "")) for item in items]
    if not all(uuids):
        raise AssertionError(f"{item_name} UUIDs must be nonempty")
    if len(set(uuids)) != len(uuids):
        raise AssertionError(f"{item_name} UUIDs must be unique")
    return uuids


def exact_label_selectors(labels: list[dict[str, Any]]) -> list[dict[str, str | float]]:
    selectors: list[dict[str, str | float]] = []
    for label in labels:
        net = str(label.get("net", ""))
        try:
            x = float(label["x"])
            y = float(label["y"])
        except (KeyError, TypeError, ValueError) as error:
            raise AssertionError(f"label delete selector is incomplete: {label}") from error
        if not net:
            raise AssertionError(f"label delete selector has no net: {label}")
        selectors.append({"net": net, "x": x, "y": y})
    identities = {(selector["net"], selector["x"], selector["y"]) for selector in selectors}
    if len(identities) != len(selectors):
        raise AssertionError("label delete selectors must be unique")
    return selectors


def classify_known_diagnostics(layout: dict[str, Any], orphans: dict[str, Any]) -> dict[str, Any]:
    count = int(orphans.get("orphan_count", -1))
    if layout["wire_count"] == 0 and count == layout["label_count"]:
        return {"orphan_labels": count, "classification": "pin_end_labels"}
    raise AssertionError(
        f"unexpected orphan diagnostic: count={count}, wires={layout['wire_count']}, labels={layout['label_count']}"
    )


def _count_no_connect_markers(schematic: Path) -> int:
    return len(re.findall(r"\(\s*no_connect\b", schematic.read_text()))


def _load_acceptance_toolsets(client: McpClient) -> None:
    schemas = {
        toolset: client.tool_schemas(toolset)
        for toolset in ("sch_components", "sch_batch", "sch_analysis", "sch_export")
    }
    contracts = {
        "list_schematic_components": ("sch_components", ("schematic",), ("schematic",)),
        "get_schematic_layout": ("sch_batch", ("schematic",), ("schematic",)),
        "validate_wire_connections": ("sch_batch", ("schematic",), ("schematic",)),
        "validate_component_connections": ("sch_batch", ("schematic",), ("schematic",)),
        "export_netlist_summary": ("sch_export", ("schematic",), ("schematic",)),
        "run_erc": ("sch_export", ("schematic",), ("schematic", "severity")),
        "export_schematic_svg": ("sch_export", ("schematic", "output"), ("schematic", "output")),
        "list_schematic_wires": ("sch_analysis", ("schematic",), ("schematic",)),
        "list_schematic_labels": ("sch_analysis", ("schematic",), ("schematic",)),
        "check_schematic_overlaps": ("sch_analysis", ("schematic",), ("schematic",)),
        "find_orphan_items": ("sch_analysis", ("schematic",), ("schematic",)),
        "find_shorted_nets": ("sch_analysis", ("schematic",), ("schematic",)),
        "find_single_pin_nets": ("sch_analysis", ("schematic",), ("schematic",)),
        "get_pin_net_name": ("sch_analysis", ("schematic", "reference", "pin_number"), ("schematic", "reference", "pin_number")),
    }
    missing = {}
    for tool, (toolset, required_inputs, property_inputs) in contracts.items():
        schema = schemas[toolset].get(tool)
        if schema is None:
            missing[tool] = ["tool"]
            continue
        absent_required = set(required_inputs) - set(schema.get("required", []))
        absent_properties = set(property_inputs) - set(schema.get("properties", {}))
        absent = sorted(absent_required | absent_properties)
        if absent:
            missing[tool] = absent
    if missing:
        raise RuntimeError(f"Konnect acceptance query contract mismatch: {missing}")


def require_production_capabilities(client: McpClient) -> None:
    """Fail closed on every production prerequisite before deletion begins."""
    require_schematic_capabilities(client)
    _load_acceptance_toolsets(client)
    schema = client.tool_schemas("sch_wiring").get("delete_schematic_net_label")
    if schema is None:
        raise RuntimeError("missing Konnect production tool: delete_schematic_net_label")
    missing_required = {"schematic", "net", "x", "y"} - set(schema.get("required", []))
    missing_properties = {"schematic", "net", "x", "y"} - set(schema.get("properties", {}))
    if missing_required or missing_properties:
        raise RuntimeError(
            "Konnect production input contract mismatch: "
            f"delete_schematic_net_label required={sorted(missing_required)} "
            f"properties={sorted(missing_properties)}"
        )


def _query(client: McpClient, schematic: Path, svg_output: Path) -> dict[str, Any]:
    _load_acceptance_toolsets(client)
    args = {"schematic": str(schematic)}
    layout = client.call_tool_json("get_schematic_layout", args)
    if "no_connect_count" not in layout:
        layout["no_connect_count"] = _count_no_connect_markers(schematic)
    data = {
        "components": client.call_tool_json("list_schematic_components", args),
        "netlist": client.call_tool_json("export_netlist_summary", args),
        "layout": layout,
        "wires": client.call_tool_json("list_schematic_wires", args),
        "labels": client.call_tool_json("list_schematic_labels", args),
        "overlaps": client.call_tool_json("check_schematic_overlaps", args),
        "orphans": client.call_tool_json("find_orphan_items", args),
        "shorts": client.call_tool_json("find_shorted_nets", args),
        "single_pin_nets": client.call_tool_json("find_single_pin_nets", args),
        "wire_validation": client.call_tool_json("validate_wire_connections", args),
        "component_validation": client.call_tool_json("validate_component_connections", args),
        "erc": client.call_tool_json("run_erc", {**args, "severity": "info"}),
        "svg": client.call_tool_json("export_schematic_svg", {**args, "output": str(svg_output)}),
    }
    exported = svg_output if svg_output.is_file() else svg_output.parent / f"{schematic.stem}.svg"
    if not exported.is_file():
        raise AssertionError(f"SVG export missing: {exported}")
    data["svg_path"] = str(exported)
    data["semantic"] = exported_net_semantics(data["netlist"])
    return data


def _inventory(components: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for component in components:
        reference = component["reference"]
        if reference == "U1":
            counts["mcu"] += 1
        elif reference.startswith("SW"):
            counts["switch"] += 1
        elif reference.startswith("D"):
            counts["diode"] += 1
        elif reference.startswith("J"):
            counts["connector"] += 1
        elif reference.startswith("#FLG"):
            counts["flag"] += 1
    return dict(counts)


def normalize_actual_components(components: list[dict[str, Any]]) -> list[dict[str, str]]:
    return sorted(
        [
            {key: str(component.get(key, "")) for key in ("reference", "lib_id", "value", "footprint")}
            for component in components
        ],
        key=lambda item: item["reference"],
    )


def normalize_exported_pins(netlist: dict[str, Any]) -> list[dict[str, str]]:
    assignments = [
        {"reference": str(component["reference"]), "pin_number": str(pin["number"]), "net_name": str(pin["net"])}
        for component in netlist.get("components", [])
        for pin in component.get("pins", [])
        if pin.get("net")
    ]
    return sorted(assignments, key=lambda item: (item["net_name"], item["reference"], int(item["pin_number"])))


def exported_net_semantics(netlist: dict[str, Any]) -> dict[str, Any]:
    pins_by_net: dict[str, list[dict[str, str]]] = {}
    for assignment in normalize_exported_pins(netlist):
        pins_by_net.setdefault(assignment["net_name"], []).append({
            "reference": assignment["reference"], "pin_number": assignment["pin_number"],
        })
    return {"nets": [{"name": name, "pins": pins} for name, pins in pins_by_net.items()]}


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list).encode()
    ).hexdigest()


def _expected_component_hash() -> str:
    return _stable_hash(
        normalize_actual_components(
            [
                {
                    "reference": component.reference,
                    "lib_id": component.lib_id,
                    "value": component.value,
                    "footprint": component.footprint,
                }
                for component in build_schematic_plan().components
            ]
        )
    )


def _expected_pin_hash() -> str:
    return _stable_hash(
        normalize_exported_pins(
            {
                "components": [
                    {
                        "reference": connection.reference,
                        "pins": [{"number": connection.pin_number, "net": connection.net_name}],
                    }
                    for connection in build_schematic_plan().connections
                ]
            }
        )
    )


def assert_frozen_acceptance(data: dict[str, Any]) -> None:
    """Check live candidate/production facts against the reviewed plan."""
    components = normalize_actual_components(data["components"]["components"])
    expected_component_hash = FROZEN_COMPONENT_SHA256 or _expected_component_hash()
    if _stable_hash(components) != expected_component_hash:
        raise AssertionError("component contract mismatch")
    svg = Path(data["svg_path"]).read_text()
    page = re.search(r'width="([0-9.]+)mm" height="([0-9.]+)mm"', svg)
    if page is None or not (419.0 <= float(page.group(1)) <= 421.0 and 296.0 <= float(page.group(2)) <= 298.0):
        raise AssertionError("page contract mismatch: expected A3 landscape SVG")
    if data["overlaps"].get("overlap_count") != 0:
        raise AssertionError(f"overlap contract mismatch: {data['overlaps']}")
    single_pin = data["single_pin_nets"]
    if single_pin.get("single_pin_net_count") != 0 or single_pin.get("nets") != []:
        raise AssertionError(f"single-pin contract mismatch: {single_pin}")
    assignments = normalize_exported_pins(data["netlist"])
    expected_pin_hash = FROZEN_PIN_SHA256 or _expected_pin_hash()
    if _stable_hash(assignments) != expected_pin_hash:
        raise AssertionError("pin contract mismatch")
    net_names = {assignment["net_name"] for assignment in assignments}
    prohibited = net_names & PROHIBITED_NETS
    if prohibited:
        raise AssertionError(f"prohibited FFC net present: {sorted(prohibited)}")
    actual_semantic = normalize_net_semantics(exported_net_semantics(data["netlist"]))
    for reference, pin_map in FROZEN_CONNECTOR_MAP.items():
        for pin_number, net_name in pin_map:
            if (reference, str(pin_number)) not in actual_semantic.get(net_name, ()):
                raise AssertionError(f"connector map mismatch: {reference}.{pin_number} -> {net_name}")


def record_visual_approval(
    evidence_path: Path, output_path: Path, approved_by: str, checklist: dict[str, bool],
) -> dict[str, Any]:
    """Record, but never infer, a human visual approval for candidate evidence."""
    evidence = json.loads(evidence_path.read_text())
    if not approved_by.strip():
        raise AssertionError("visual approval requires reviewer identity")
    if set(checklist) != VISUAL_CHECKLIST or not all(checklist.values()):
        raise AssertionError("visual approval checklist incomplete")
    approval = {
        "approved": True,
        "approved_by": approved_by,
        "checklist": checklist,
        **{field: evidence.get(field) for field in ("plan_hash", "git_sha", "svg_sha256", "render_sha256")},
    }
    if not all(approval[field] for field in ("plan_hash", "git_sha", "svg_sha256", "render_sha256")):
        raise AssertionError("visual approval evidence hashes missing")
    evidence["visual_approval"] = approval
    _write_json(output_path, evidence)
    return evidence


def _assert_acceptance(data: dict[str, Any]) -> dict[str, Any]:
    components = data["components"]["components"]
    layout = data["layout"]
    inventory = _inventory(components)
    if inventory != EXPECTED_INVENTORY or len(components) != 146:
        raise AssertionError(f"inventory mismatch: {inventory}, total={len(components)}")
    refs = [component["reference"] for component in components]
    state = {
        "layout": layout,
        "wire_uuids": assert_unique_nonempty_uuids(data["wires"]["wires"], "wire"),
        "label_selectors": data["labels"]["labels"],
        "references": refs,
    }
    assert_current_production_state(state)
    if any("TestPoint" in component.get("footprint", "") for component in components):
        raise AssertionError("TestPoint footprint remains")
    if layout["wire_count"] != 0 or layout["label_count"] != 313:
        raise AssertionError(f"layout mismatch: {layout['wire_count']} wires, {layout['label_count']} labels")
    if layout.get("no_connect_count") != 1:
        raise AssertionError(f"no-connect mismatch: {layout}")
    if data["shorts"].get("short_count") != 0:
        raise AssertionError(f"shorted nets: {data['shorts']}")
    if not data["wire_validation"].get("valid") or not data["component_validation"].get("valid"):
        raise AssertionError("wire or component validation failed")
    if data["erc"].get("errors") != 0 or data["erc"].get("warnings") != 0:
        raise AssertionError(f"ERC failures: {data['erc']}")
    diagnostics = classify_known_diagnostics(layout, data["orphans"])
    assert_frozen_acceptance(data)
    return {"inventory": inventory, "known_diagnostics": diagnostics}


def acceptance_record(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a full read-only query into reusable acceptance evidence."""
    return {
        "acceptance": _assert_acceptance(data),
        "gates": {
            "wire_validation": data["wire_validation"].get("valid") is True,
            "component_validation": data["component_validation"].get("valid") is True,
            "erc_errors": data["erc"].get("errors"),
            "erc_warnings": data["erc"].get("warnings"),
        },
        "semantic": normalize_net_semantics(data["semantic"]),
        "svg_path": data["svg_path"],
        "svg_sha256": hashlib.sha256(Path(data["svg_path"]).read_bytes()).hexdigest(),
    }


def normalize_net_semantics(netlist: dict[str, Any]) -> dict[str, tuple[tuple[str, str], ...]]:
    """Return stable net-to-pin semantics across tool output ordering variants."""
    if "nets" not in netlist:
        return {
            str(name): tuple(sorted((str(reference), str(pin)) for reference, pin in pins))
            for name, pins in sorted(netlist.items())
        }
    nets = netlist["nets"]
    if isinstance(nets, dict):
        iterable = [
            {"name": name, "pins": pins}
            for name, pins in nets.items()
        ]
    else:
        iterable = nets
    normalized = {}
    for item in iterable:
        if isinstance(item, str):
            normalized[item] = ()
            continue
        name = item.get("name", item.get("net_name"))
        if not name:
            raise AssertionError(f"netlist item has no name: {item}")
        pins = tuple(sorted(
            (str(pin["reference"]), str(pin["pin_number"]))
            for pin in item.get("pins", [])
        ))
        normalized[str(name)] = pins
    return dict(sorted(normalized.items()))


def assert_semantically_equal(left: dict[str, Any], right: dict[str, Any]) -> None:
    left_normalized = normalize_net_semantics(left)
    right_normalized = normalize_net_semantics(right)
    if left_normalized != right_normalized:
        raise AssertionError(
            f"semantic mismatch: left={left_normalized}, right={right_normalized}"
        )


def assert_candidate_evidence(
    evidence: dict[str, Any],
    expected_plan_hash: str,
    expected_git_sha: str,
) -> None:
    """Fail closed unless candidate and reviewed render bind to this exact code."""
    if not evidence:
        raise AssertionError("candidate evidence is required")
    for field, expected in (
        ("plan_hash", expected_plan_hash),
        ("git_sha", expected_git_sha),
    ):
        if evidence.get(field) != expected:
            raise AssertionError(f"candidate evidence {field} mismatch")
    gates = evidence.get("gates", {})
    expected_gates = {
        "wire_validation": True,
        "component_validation": True,
        "erc_errors": 0,
        "erc_warnings": 0,
    }
    if any(gates.get(field) != expected for field, expected in expected_gates.items()):
        raise AssertionError(f"candidate evidence gates mismatch: {gates}")
    if not evidence.get("acceptance") or not evidence.get("svg_sha256") or not evidence.get("render_sha256"):
        raise AssertionError("candidate evidence acceptance or render hashes missing")
    approval = evidence.get("visual_approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise AssertionError("candidate evidence visual approval missing")
    for field in ("plan_hash", "git_sha", "svg_sha256", "render_sha256"):
        if approval.get(field) != evidence.get(field):
            raise AssertionError(f"candidate evidence visual approval {field} mismatch")


def _assert_schematic_state(
    state: dict[str, Any], baseline: dict[str, int], references: frozenset[str], description: str,
) -> None:
    layout = state["layout"]
    if {key: layout.get(key) for key in baseline} != baseline:
        raise AssertionError(f"{description} baseline mismatch: {layout}")
    if len(state["wire_uuids"]) != baseline["wire_count"]:
        raise AssertionError(f"{description} wire UUID count mismatch")
    label_items = state.get("label_selectors", state.get("label_uuids", []))
    if len(label_items) != baseline["label_count"]:
        raise AssertionError(f"{description} label count mismatch")
    if len(state["references"]) != len(references) or set(state["references"]) != references:
        raise AssertionError(f"{description} references mismatch")


def assert_current_production_state(state: dict[str, Any]) -> None:
    _assert_schematic_state(
        state, CURRENT_ACCEPTANCE_BASELINE, EXPECTED_PRODUCTION_REFERENCES, "production",
    )
    if any(reference.startswith("TP") for reference in state["references"]):
        raise AssertionError("production TestPoint inventory mismatch")


def assert_current_155_preflight(state: dict[str, Any]) -> None:
    _assert_schematic_state(
        state, CURRENT_155_BASELINE, CURRENT_155_REFERENCES, "current 155 source",
    )
    forbidden_after_migration = {"U1", *{f"J{index}" for index in range(2, 7)}, *{f"#FLG{index:02d}" for index in range(1, 4)}}
    if not forbidden_after_migration <= set(state["references"]):
        raise AssertionError("current 155 source missing retired active-board references")


def _working_tree_is_clean() -> bool:
    return not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()


def _writer_pids(path: Path, *, run_fn=subprocess.run) -> list[str]:
    try:
        result = run_fn(
            ["lsof", "-t", "--", str(path)],
            text=True, capture_output=True, check=False,
        )
    except (FileNotFoundError, OSError) as error:
        raise RuntimeError("writer detection unavailable") from error
    return [line for line in result.stdout.splitlines() if line]


def assert_predelete_safety(
    schematic: Path, board: Path, *, clean_tree_fn=_working_tree_is_clean, writer_pids_fn=_writer_pids,
) -> dict[str, str]:
    """Record immutable PCB evidence and refuse concurrent or dirty mutation."""
    if not clean_tree_fn():
        raise AssertionError("production working tree must be clean before delete")
    writers = writer_pids_fn(schematic)
    if writers:
        raise AssertionError(f"production schematic has active writer(s): {writers}")
    return {
        "schematic_sha256": hashlib.sha256(schematic.read_bytes()).hexdigest(),
        "pcb_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
    }


def _component_identity_fingerprint(components: list[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    identities = tuple(
        sorted(
            (str(component.get("reference", "")), str(component.get("uuid", "")))
            for component in components
        )
    )
    if len({reference for reference, _uuid in identities}) != len(identities):
        raise AssertionError("component identity references must be unique")
    if len({_uuid for _reference, _uuid in identities}) != len(identities):
        raise AssertionError("component identity uuids must be unique")
    if any(not reference or not uuid for reference, uuid in identities):
        raise AssertionError("component identity references and uuids must be nonempty")
    return identities


def _component_contract_hash_from_components(components: list[dict[str, Any]]) -> str:
    return _stable_hash(normalize_actual_components(components))


def _pin_contract_hash_from_schematic(client: McpClient, schematic: Path) -> str:
    netlist = client.call_tool_json("export_netlist_summary", {"schematic": str(schematic)})
    return _stable_hash(normalize_exported_pins(netlist))


def prepare_candidate_libraries(
    client_factory, project_dir: Path, *, apply_core_fn=apply_core_library, apply_interconnect_fn=apply_interconnect_library,
    capability_fn=require_schematic_capabilities,
) -> None:
    """Regenerate shared source libraries with isolated clients."""
    with client_factory(KONNECT, CONFIG) as client:
        capability_fn(client)
        apply_core_fn(client)
    with client_factory(KONNECT, CONFIG) as client:
        capability_fn(client)
        apply_interconnect_fn(client)


def verify_candidate_libraries(
    client_factory, project: Path, *, capability_fn=require_schematic_capabilities,
) -> dict[str, list[str]]:
    """Query registered candidate libraries through a fresh client.

    Symbols resolve against the candidate project directory; footprints use the
    registered project file path.
    """
    symbols = ("Conn_01x03", "Conn_01x04", "Conn_01x05", INTERCONNECT_SYMBOL_NAME)
    footprints = (
        "PinHeader_1x03_P2.54mm_Vertical",
        "PinHeader_1x04_P2.54mm_Vertical",
        "PinHeader_1x05_P2.54mm_Vertical",
        INTERCONNECT_SYMBOL_NAME,
    )
    project_dir = project.parent
    with client_factory(KONNECT, CONFIG) as client:
        client.tool_schemas("library")
        for name in symbols:
            library = "lh60-interconnect" if name == INTERCONNECT_SYMBOL_NAME else "lh60-core"
            result = client.call_tool_json(
                "get_symbol_info", {"lib_id": f"{library}:{name}", "project_dir": str(project_dir)}
            )
            if result.get("name") != name:
                raise AssertionError(f"library symbol verification failed: {name}")
        for name in footprints:
            root = INTERCONNECT_FOOTPRINT_LIBRARY if name == INTERCONNECT_SYMBOL_NAME else CORE_FOOTPRINT_LIBRARY
            result = client.call_tool_json(
                "get_footprint_info",
                {"footprint_path": str(root / f"{name}.kicad_mod"), "include_graphics": True, "project": str(project)},
            )
            if result.get("name") != name:
                raise AssertionError(f"library footprint verification failed: {name}")
    return {"symbols": list(symbols), "footprints": list(footprints)}


def current_155_preflight(client: McpClient, schematic: Path) -> dict[str, Any]:
    """Query the current active-MCU source baseline before one-way migration."""
    _load_acceptance_toolsets(client)
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    wires = client.call_tool_json("list_schematic_wires", {"schematic": str(schematic)})["wires"]
    labels = client.call_tool_json("list_schematic_labels", {"schematic": str(schematic)})["labels"]
    wire_uuids = assert_unique_nonempty_uuids(wires, "wire")
    label_selectors = exact_label_selectors(labels)
    refs = [item["reference"] for item in client.call_tool_json("list_schematic_components", {"schematic": str(schematic)})["components"]]
    state = {"layout": layout, "wire_uuids": wire_uuids, "label_selectors": label_selectors, "references": refs}
    assert_current_155_preflight(state)
    return state


def passive_ffc_converge(client: McpClient, schematic: Path, state: dict[str, Any]) -> None:
    require_schematic_capabilities(client)
    if state["wire_uuids"]:
        client.call_tool("batch_delete_schematic_wire", {"schematic": str(schematic), "uuids": state["wire_uuids"]})
    for selector in state["label_selectors"]:
        client.call_tool("delete_schematic_net_label", {"schematic": str(schematic), **selector})
    client.call_tool("batch_delete_schematic_components", {"schematic": str(schematic), "references": state["references"]})
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    if any(layout.get(key) != 0 for key in ("component_count", "wire_count", "label_count", "no_connect_count")):
        raise AssertionError(f"passive FFC migration delete did not empty schematic: {layout}")
    apply_schematic(client, schematic)


def _evidence_path(path: Path | None) -> Path:
    if path is None:
        raise AssertionError("candidate evidence is required before production deletion")
    if not path.is_file():
        raise AssertionError(f"candidate evidence missing: {path}")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _query_acceptance_record(
    client: McpClient, schematic: Path, svg_output: Path,
) -> dict[str, Any]:
    return acceptance_record(_query(client, schematic, svg_output))


def run_production_transaction(
    client: McpClient,
    schematic: Path,
    candidate_evidence_path: Path | None,
    output_path: Path,
    *,
    expected_plan_hash: str | None = None,
    expected_git_sha: str | None = None,
    preflight_fn=current_155_preflight,
    converge_fn=passive_ffc_converge,
    acceptance_fn=_query_acceptance_record,
    candidate_fn=None,
    candidate_acceptance_fn=_query_acceptance_record,
    capabilities_fn=require_production_capabilities,
    safety_fn=assert_predelete_safety,
) -> dict[str, Any]:
    """Execute the one-way production transaction only after bound review evidence."""
    evidence_file = _evidence_path(candidate_evidence_path)
    candidate_evidence = json.loads(evidence_file.read_text())
    expected_plan_hash = expected_plan_hash or _plan_hash()
    expected_git_sha = expected_git_sha or _git_sha()
    candidate_fn = candidate_fn or candidate
    assert_candidate_evidence(candidate_evidence, expected_plan_hash, expected_git_sha)
    capabilities_fn(client)
    safety = safety_fn(schematic, BOARD)

    state = preflight_fn(client, schematic)
    assert_current_155_preflight(state)
    converge_fn(client, schematic, state)

    with tempfile.TemporaryDirectory(prefix="lh60-production-acceptance.") as directory:
        output_directory = Path(directory)
        production = acceptance_fn(client, schematic, output_directory / "production.svg")
        candidate_schematic = candidate_fn(
            client, output_directory / "candidate", regenerate_libraries=False,
        )
        candidate_record = candidate_acceptance_fn(
            client, candidate_schematic, output_directory / "candidate.svg"
        )
    assert_semantically_equal(production["semantic"], candidate_record["semantic"])
    result = {
        "mode": "production-transaction",
        "schematic": str(schematic),
        "plan_hash": expected_plan_hash,
        "git_sha": expected_git_sha,
        "candidate_evidence_path": str(evidence_file),
        "candidate_evidence": candidate_evidence,
        "predelete_safety": safety,
        "preflight": state,
        "production": production,
        "second_candidate": candidate_record,
    }
    _write_json(output_path, result)
    return result


def candidate_library_registrations(project: str) -> dict[str, list[dict[str, str]]]:
    return {
        "symbols": [
            {"nickname": "lh60-core", "library_path": str(ROOT / "lib/lh60-core/lh60-core.kicad_sym"), "project": project},
            {"nickname": "lh60-interconnect", "library_path": str(INTERCONNECT_SYMBOL_LIBRARY), "project": project},
        ],
        "footprints": [
            {"nickname": "lh60-core", "library_path": str(ROOT / "lib/lh60-core/lh60-core.pretty"), "project": project},
            {"nickname": "lh60-interconnect", "library_path": str(INTERCONNECT_FOOTPRINT_LIBRARY), "project": project},
            {"nickname": "lh60-sockets", "library_path": str(ROOT / "lib/lh60-sockets"), "project": project},
        ],
    }


def candidate(
    client: McpClient,
    directory: Path,
    *,
    regenerate_libraries: bool = False,
    regenerate_fn=prepare_candidate_libraries,
    verify_fn=verify_candidate_libraries,
    client_factory=McpClient,
    apply_fn=apply_schematic,
) -> Path:
    client.call_tool("create_project", {"path": str(directory), "name": "lh60-candidate"})
    project = directory / "lh60-candidate.kicad_pro"
    client.tool_schemas("library")
    registrations = candidate_library_registrations(str(project))
    for registration in registrations["symbols"]:
        client.call_tool("register_symbol_library", {**registration, "scope": "project", "replace_existing": True})
    for registration in registrations["footprints"]:
        client.call_tool("register_footprint_library", {**registration, "scope": "project", "replace_existing": True})
    if regenerate_libraries:
        regenerate_fn(client_factory, directory)
    verify_fn(client_factory, project)
    schematic = directory / "lh60-candidate.kicad_sch"
    apply_fn(client, schematic)
    return schematic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--candidate-evidence", type=Path)
    parser.add_argument("--render", type=Path)
    parser.add_argument("--record-visual-approval", action="store_true")
    parser.add_argument("--approved-by")
    parser.add_argument("--visual-checklist", type=Path)
    args = parser.parse_args()
    selected_modes = [
        args.production,
        args.preflight,
    ]
    if sum(1 for enabled in selected_modes if enabled) > 1:
        parser.error("--production and --preflight are mutually exclusive")
    if args.record_visual_approval:
        if not args.candidate_evidence or not args.output or not args.approved_by or not args.visual_checklist:
            parser.error("--record-visual-approval requires --candidate-evidence, --output, --approved-by, and --visual-checklist")
        checklist = json.loads(args.visual_checklist.read_text())
        result = record_visual_approval(args.candidate_evidence, args.output, args.approved_by, checklist)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    schematic = SCHEMATIC if (args.production or args.preflight) else None
    with McpClient(KONNECT, CONFIG) as client:
        if schematic is None:
            directory = args.candidate_dir or Path(tempfile.mkdtemp(prefix="lh60-debug-sch."))
            directory.mkdir(parents=True, exist_ok=True)
            schematic = candidate(client, directory)
        svg_output = Path(tempfile.mkdtemp(prefix="lh60-sch-svg.")) / "lh60.svg"
        data = _query(client, schematic, svg_output)
        result = {
            "mode": "production" if (args.production or args.preflight) else "candidate",
            "schematic": str(schematic),
            "git_sha": _git_sha(),
            **acceptance_record(data),
            "queries": data,
        }
        if not (args.production or args.preflight):
            result["plan_hash"] = _plan_hash()
        if args.render:
            result["render_sha256"] = hashlib.sha256(args.render.read_bytes()).hexdigest()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
