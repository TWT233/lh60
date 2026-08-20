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
    CONNECTOR_GROUPS,
    POWER_FLAG_INSTANCE_FLAGS,
    SCHEMATIC,
    apply_power_flag_instance_flags,
    apply_schematic,
    build_schematic_plan,
    require_schematic_capabilities,
)
from tools.lh60_design.core_library import (
    FOOTPRINT_LIBRARY as CORE_FOOTPRINT_LIBRARY,
    apply_core_library,
)
from tools.lh60_design.mcu_library import (
    FOOTPRINT_LIBRARY as MCU_FOOTPRINT_LIBRARY,
    apply_mcu_library,
)


ROOT = Path(__file__).resolve().parents[1]
KONNECT = Path("/data00/home/wangqiyilang/.local/bin/konnect")
CONFIG = Path.home() / ".config/konnect/config.toml"
BOARD = ROOT / "lh60.kicad_pcb"
EXPECTED_BASELINE = {"component_count": 172, "wire_count": 290, "label_count": 339}
EXPECTED_INVENTORY = {"mcu": 1, "switch": 75, "diode": 70, "connector": 6, "flag": 3}
EXPECTED_PRODUCTION_TESTPOINTS = {f"TP{index}" for index in range(1, 24)}
EXPECTED_PRODUCTION_REFERENCES = (
    {"U1", *{f"#FLG{index:02d}" for index in range(1, 4)}}
    | {f"D{index}" for index in range(1, 71)}
    | {f"SW{index}" for index in range(1, 77) if index != 59}
    | EXPECTED_PRODUCTION_TESTPOINTS
)
FROZEN_COMPONENT_SHA256 = "028d14843b05b9483765e68bb59fc9e5bd8e0d8b9a2e60b539314c6578c79d18"
FROZEN_PIN_SHA256 = "85f400c94abdb1e70a6da80177fbba76b774a3105d0b15081b54f318a06d7f58"
FROZEN_CONNECTOR_MAP = {
    "J1": (("1", "VSYS"), ("2", "3V3"), ("3", "GND")),
    "J2": (("1", "COL0"), ("2", "COL1"), ("3", "COL2"), ("4", "COL3"), ("5", "COL4")),
    "J3": (("1", "COL5"), ("2", "COL6"), ("3", "COL7"), ("4", "COL8"), ("5", "COL9")),
    "J4": (("1", "ROW0"), ("2", "ROW1"), ("3", "ROW2"), ("4", "ROW3")),
    "J5": (("1", "ROW4"), ("2", "ROW5"), ("3", "ROW6")),
    "J6": (("1", "GP27"), ("2", "GP28"), ("3", "GP29")),
}
VISUAL_CHECKLIST = {"u1", "matrix", "connectors", "title_block"}
POWER_FLAG_INSTANCE_CONTRACT = {
    "schematic_sha256": "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
    "component_sha256": FROZEN_COMPONENT_SHA256,
    "pin_sha256": FROZEN_PIN_SHA256,
    "pcb_sha256": "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
    "flags": POWER_FLAG_INSTANCE_FLAGS,
}


def _plan_hash() -> str:
    plan = build_schematic_plan()
    payload = {
        "components": [component.__dict__ for component in plan.components],
        "connections": [connection.__dict__ for connection in plan.connections],
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


def classify_known_diagnostics(layout: dict[str, Any], orphans: dict[str, Any]) -> dict[str, Any]:
    count = int(orphans.get("orphan_count", -1))
    if layout["wire_count"] == 0 and count == layout["label_count"]:
        return {"orphan_labels": count, "classification": "pin_end_labels"}
    raise AssertionError(
        f"unexpected orphan diagnostic: count={count}, wires={layout['wire_count']}, labels={layout['label_count']}"
    )


def _load_acceptance_toolsets(client: McpClient) -> None:
    schemas = {
        toolset: client.tool_schemas(toolset)
        for toolset in ("sch_components", "sch_batch", "sch_wiring", "sch_analysis", "sch_export")
    }
    contracts = {
        "list_schematic_components": ("sch_components", ("schematic",), ("schematic",)),
        "get_schematic_layout": ("sch_batch", ("schematic",), ("schematic",)),
        "validate_wire_connections": ("sch_batch", ("schematic",), ("schematic",)),
        "validate_component_connections": ("sch_batch", ("schematic",), ("schematic",)),
        "batch_delete_schematic_wire": ("sch_wiring", ("schematic", "uuids"), ("schematic", "uuids")),
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
    contracts = {
        "update_pcb_from_schematic": (
            client.tool_schemas("sch_export"),
            ("schematic", "board"),
            ("schematic", "board", "dry_run", "expected_plan_revision"),
        ),
        "flip_component": (
            client.tool_schemas("pcb_components"),
            ("board", "reference", "layer"),
            ("board", "reference", "layer"),
        ),
    }
    missing = {}
    for tool, (schemas, required_inputs, property_inputs) in contracts.items():
        schema = schemas.get(tool)
        if schema is None:
            missing[tool] = ["tool"]
            continue
        absent = sorted(
            (set(required_inputs) - set(schema.get("required", [])))
            | (set(property_inputs) - set(schema.get("properties", {})))
        )
        if absent:
            missing[tool] = absent
    if missing:
        raise RuntimeError(f"Konnect production capability mismatch: {missing}")


def _query(client: McpClient, schematic: Path, svg_output: Path) -> dict[str, Any]:
    _load_acceptance_toolsets(client)
    args = {"schematic": str(schematic)}
    data = {
        "components": client.call_tool_json("list_schematic_components", args),
        "netlist": client.call_tool_json("export_netlist_summary", args),
        "layout": client.call_tool_json("get_schematic_layout", args),
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


def assert_frozen_acceptance(data: dict[str, Any]) -> None:
    """Check live candidate/production facts against the reviewed plan."""
    components = normalize_actual_components(data["components"]["components"])
    if _stable_hash(components) != FROZEN_COMPONENT_SHA256:
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
    if _stable_hash(assignments) != FROZEN_PIN_SHA256:
        raise AssertionError("pin contract mismatch")
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
    if inventory != EXPECTED_INVENTORY or len(components) != 155:
        raise AssertionError(f"inventory mismatch: {inventory}, total={len(components)}")
    refs = [component["reference"] for component in components]
    if len(set(refs)) != len(refs) or any(ref.startswith("TP") for ref in refs) or "SW59" in refs:
        raise AssertionError("references are not unique or contain retired debug items")
    if any("TestPoint" in component.get("footprint", "") for component in components):
        raise AssertionError("TestPoint footprint remains")
    if layout["wire_count"] != 0 or layout["label_count"] != 339:
        raise AssertionError(f"layout mismatch: {layout['wire_count']} wires, {layout['label_count']} labels")
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
    """Convert query output into the evidence needed to authorize convergence."""
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


def assert_production_preflight(
    state: dict[str, Any], expected_references: set[str] = EXPECTED_PRODUCTION_REFERENCES,
) -> None:
    layout = state["layout"]
    if {key: layout.get(key) for key in EXPECTED_BASELINE} != EXPECTED_BASELINE:
        raise AssertionError(f"production baseline mismatch: {layout}")
    for name, expected_count in (("wire", 290), ("label", 339)):
        if len(state[f"{name}_uuids"]) != expected_count:
            raise AssertionError(f"production {name} UUID count mismatch")
    if set(state["references"]) != expected_references:
        raise AssertionError("production references mismatch")
    found_testpoints = {ref for ref in state["references"] if ref.startswith("TP")}
    if found_testpoints != EXPECTED_PRODUCTION_TESTPOINTS:
        raise AssertionError("production TestPoint inventory mismatch")


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


def require_power_flag_instance_migration_capabilities(client: McpClient) -> None:
    require_schematic_capabilities(client)
    schemas = {
        toolset: client.tool_schemas(toolset)
        for toolset in ("sch_components", "sch_analysis", "sch_export")
    }
    contracts = {
        "get_schematic_component": ("sch_components", ("schematic", "reference"), ("schematic", "reference")),
        "list_schematic_components": ("sch_components", ("schematic",), ("schematic",)),
        "list_schematic_wires": ("sch_analysis", ("schematic",), ("schematic",)),
        "list_schematic_labels": ("sch_analysis", ("schematic",), ("schematic",)),
        "export_netlist_summary": ("sch_export", ("schematic",), ("schematic",)),
    }
    missing = {}
    for tool, (toolset, required_inputs, property_inputs) in contracts.items():
        schema = schemas[toolset].get(tool)
        if schema is None:
            missing[tool] = ["tool"]
            continue
        absent = sorted(
            (set(required_inputs) - set(schema.get("required", [])))
            | (set(property_inputs) - set(schema.get("properties", {})))
        )
        if absent:
            missing[tool] = absent
    if missing:
        raise RuntimeError(f"Konnect power-flag migration capability mismatch: {missing}")


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


def _flag_state_map(components: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state = {}
    for component in components:
        reference = str(component.get("reference", ""))
        state[reference] = {
            "uuid": str(component.get("uuid", "")),
            "in_bom": component.get("in_bom"),
            "on_board": component.get("on_board"),
            "dnp": component.get("dnp"),
        }
    return state


def _power_flag_identity_components(client: McpClient, schematic: Path, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    listed_references = [str(component.get("reference", "")) for component in components]
    power_flag_references = [
        reference
        for reference in listed_references
        if reference in POWER_FLAG_INSTANCE_FLAGS
    ]
    expected_references = sorted(POWER_FLAG_INSTANCE_FLAGS)
    if sorted(power_flag_references) != expected_references:
        raise AssertionError("power flag reference set mismatch")

    identities = []
    for reference in expected_references:
        detail = client.call_tool_json(
            "get_schematic_component",
            {"schematic": str(schematic), "reference": reference},
        )
        if str(detail.get("reference", "")) != reference:
            raise AssertionError(f"power flag identity mismatch for {reference}")
        identities.append({"reference": reference, "uuid": str(detail.get("uuid", ""))})
    _component_identity_fingerprint(identities)
    return identities


def _query_power_flag_instance_state(client: McpClient, schematic: Path) -> dict[str, Any]:
    components = client.call_tool_json("list_schematic_components", {"schematic": str(schematic)})["components"]
    identities = _power_flag_identity_components(client, schematic, components)
    identity_by_reference = {item["reference"]: item["uuid"] for item in identities}
    flag_states = {
        reference: {**state, "uuid": identity_by_reference[reference]}
        for reference, state in _flag_state_map(components).items()
        if reference in POWER_FLAG_INSTANCE_FLAGS
    }
    wires = client.call_tool_json("list_schematic_wires", {"schematic": str(schematic)})["wires"]
    labels = client.call_tool_json("list_schematic_labels", {"schematic": str(schematic)})["labels"]
    return {
        "components": components,
        "component_identities": _component_identity_fingerprint(identities),
        "wire_uuids": assert_unique_nonempty_uuids(wires, "wire"),
        "label_uuids": assert_unique_nonempty_uuids(labels, "label"),
        "flag_states": flag_states,
        "all_flags": _flag_state_map(components),
    }


def assert_power_flag_migration_post_state(before: dict[str, Any], after: dict[str, Any]) -> None:
    if "component_identities" not in before:
        before = {
            **before,
            "component_identities": _component_identity_fingerprint(before["components"]),
            "flag_states": {reference: state for reference, state in _flag_state_map(before["components"]).items() if reference in POWER_FLAG_INSTANCE_FLAGS},
            "all_flags": _flag_state_map(before["components"]),
        }
    if "component_identities" not in after:
        after = {
            **after,
            "component_identities": _component_identity_fingerprint(after["components"]),
            "flag_states": {reference: state for reference, state in _flag_state_map(after["components"]).items() if reference in POWER_FLAG_INSTANCE_FLAGS},
            "all_flags": _flag_state_map(after["components"]),
        }
    if before["component_identities"] != after["component_identities"]:
        raise AssertionError("component identity drift detected")
    if before["wire_uuids"] != after["wire_uuids"]:
        raise AssertionError("wire identity drift detected")
    if before["label_uuids"] != after["label_uuids"]:
        raise AssertionError("label identity drift detected")
    for reference, expected in POWER_FLAG_INSTANCE_FLAGS.items():
        if after["flag_states"].get(reference) != {
            "uuid": before["flag_states"].get(reference, {}).get("uuid", ""),
            **expected,
        }:
            raise AssertionError(f"power flag final state mismatch for {reference}")
    for reference, state in before["all_flags"].items():
        if reference in POWER_FLAG_INSTANCE_FLAGS:
            continue
        if after["all_flags"].get(reference) != state:
            raise AssertionError(f"unrelated flag drift detected for {reference}")


def _component_contract_hash_from_components(components: list[dict[str, Any]]) -> str:
    return _stable_hash(normalize_actual_components(components))


def _pin_contract_hash_from_schematic(client: McpClient, schematic: Path) -> str:
    netlist = client.call_tool_json("export_netlist_summary", {"schematic": str(schematic)})
    return _stable_hash(normalize_exported_pins(netlist))


def migrate_power_flag_instance_flags(
    client: McpClient,
    schematic: Path,
    output_path: Path,
    *,
    capabilities_fn=require_power_flag_instance_migration_capabilities,
    safety_fn=assert_predelete_safety,
    state_query_fn=_query_power_flag_instance_state,
    apply_fn=apply_power_flag_instance_flags,
    component_hash_fn=_component_contract_hash_from_components,
    pin_hash_fn=_pin_contract_hash_from_schematic,
    write_json_fn=None,
) -> dict[str, Any]:
    if write_json_fn is None:
        write_json_fn = _write_json
    capabilities_fn(client)
    safety = safety_fn(schematic, BOARD)
    if safety["schematic_sha256"] != POWER_FLAG_INSTANCE_CONTRACT["schematic_sha256"]:
        raise AssertionError("schematic SHA drift detected")
    if safety["pcb_sha256"] != POWER_FLAG_INSTANCE_CONTRACT["pcb_sha256"]:
        raise AssertionError("PCB SHA drift detected")
    before = state_query_fn(client, schematic)
    before_pin_hash = pin_hash_fn(client, schematic)
    if before_pin_hash != POWER_FLAG_INSTANCE_CONTRACT["pin_sha256"]:
        raise AssertionError("pin contract hash drift detected before migration")
    batch = apply_fn(client, schematic)
    after = state_query_fn(client, schematic)
    assert_power_flag_migration_post_state(before, after)
    component_hash = component_hash_fn(after["components"])
    if component_hash != POWER_FLAG_INSTANCE_CONTRACT["component_sha256"]:
        raise AssertionError("component contract hash drift detected")
    pin_hash = pin_hash_fn(client, schematic)
    if pin_hash != before_pin_hash:
        raise AssertionError("pin contract hash drift detected after migration")
    if pin_hash != POWER_FLAG_INSTANCE_CONTRACT["pin_sha256"]:
        raise AssertionError("pin contract hash drift detected after migration")
    result = {
        "mode": "power-flag-instance-migration",
        "schematic": str(schematic),
        "contract": POWER_FLAG_INSTANCE_CONTRACT,
        "predelete_safety": safety,
        "before": before,
        "before_pin_sha256": before_pin_hash,
        "batch": batch,
        "after": after,
        "component_sha256": component_hash,
        "pin_sha256": pin_hash,
    }
    write_json_fn(output_path, result)
    return result


def prepare_candidate_libraries(
    client_factory, project_dir: Path, *, apply_core_fn=apply_core_library, apply_mcu_fn=apply_mcu_library,
    capability_fn=require_schematic_capabilities,
) -> None:
    """Regenerate shared source libraries with isolated clients."""
    with client_factory(KONNECT, CONFIG) as client:
        capability_fn(client)
        apply_core_fn(client)
    with client_factory(KONNECT, CONFIG) as client:
        capability_fn(client)
        apply_mcu_fn(client)


def verify_candidate_libraries(
    client_factory, project: Path, *, capability_fn=require_schematic_capabilities,
) -> dict[str, list[str]]:
    """Query registered candidate libraries through a fresh client.

    Symbols resolve against the candidate project directory; footprints use the
    registered project file path.
    """
    symbols = ("Conn_01x03", "Conn_01x04", "Conn_01x05", "RP2040-Tiny")
    footprints = (
        "PinHeader_1x03_P2.54mm_Vertical",
        "PinHeader_1x04_P2.54mm_Vertical",
        "PinHeader_1x05_P2.54mm_Vertical",
        "MCU_RP2040-Tiny_SMD",
    )
    project_dir = project.parent
    with client_factory(KONNECT, CONFIG) as client:
        client.tool_schemas("library")
        for name in symbols:
            library = "lh60-mcu" if name == "RP2040-Tiny" else "lh60-core"
            result = client.call_tool_json(
                "get_symbol_info", {"lib_id": f"{library}:{name}", "project_dir": str(project_dir)}
            )
            if result.get("name") != name:
                raise AssertionError(f"library symbol verification failed: {name}")
        for name in footprints:
            root = MCU_FOOTPRINT_LIBRARY if name == "MCU_RP2040-Tiny_SMD" else CORE_FOOTPRINT_LIBRARY
            result = client.call_tool_json(
                "get_footprint_info",
                {"footprint_path": str(root / f"{name}.kicad_mod"), "include_graphics": True, "project": str(project)},
            )
            if result.get("name") != name:
                raise AssertionError(f"library footprint verification failed: {name}")
    return {"symbols": list(symbols), "footprints": list(footprints)}


def preflight(client: McpClient, schematic: Path) -> dict[str, Any]:
    _load_acceptance_toolsets(client)
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    wires = client.call_tool_json("list_schematic_wires", {"schematic": str(schematic)})["wires"]
    labels = client.call_tool_json("list_schematic_labels", {"schematic": str(schematic)})["labels"]
    wire_uuids = assert_unique_nonempty_uuids(wires, "wire")
    label_uuids = assert_unique_nonempty_uuids(labels, "label")
    refs = [item["reference"] for item in client.call_tool_json("list_schematic_components", {"schematic": str(schematic)})["components"]]
    state = {"layout": layout, "wire_uuids": wire_uuids, "label_uuids": label_uuids, "references": refs}
    assert_production_preflight(state)
    return state


def converge(client: McpClient, schematic: Path, state: dict[str, Any]) -> None:
    require_schematic_capabilities(client)
    client.call_tool("batch_delete_schematic_wire", {"schematic": str(schematic), "uuids": state["wire_uuids"]})
    client.call_tool("batch_delete", {"schematic": str(schematic), "uuids": state["label_uuids"]})
    client.call_tool("batch_delete_schematic_components", {"schematic": str(schematic), "references": state["references"]})
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    if any(layout.get(key) != 0 for key in ("component_count", "wire_count", "label_count")):
        raise AssertionError(f"convergence delete did not empty schematic: {layout}")
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
    expected_references: set[str] | None = None,
    preflight_fn=preflight,
    converge_fn=converge,
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
    assert_production_preflight(
        state, expected_references if expected_references is not None else EXPECTED_PRODUCTION_REFERENCES
    )
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
            {"nickname": "lh60-mcu", "library_path": str(ROOT / "lib/lh60-mcu/lh60-mcu.kicad_sym"), "project": project},
        ],
        "footprints": [
            {"nickname": "lh60-core", "library_path": str(ROOT / "lib/lh60-core/lh60-core.pretty"), "project": project},
            {"nickname": "lh60-mcu", "library_path": str(ROOT / "lib/lh60-mcu/lh60-mcu.pretty"), "project": project},
            {"nickname": "lh60-sockets", "library_path": str(ROOT / "lib/lh60-sockets"), "project": project},
        ],
    }


def candidate(
    client: McpClient,
    directory: Path,
    *,
    regenerate_libraries: bool = True,
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
    parser.add_argument("--migrate-power-flag-instance-flags", action="store_true")
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
        args.migrate_power_flag_instance_flags,
    ]
    if sum(1 for enabled in selected_modes if enabled) > 1:
        parser.error("--production, --preflight, and --migrate-power-flag-instance-flags are mutually exclusive")
    if args.production and args.candidate_evidence is None:
        parser.error("--production requires --candidate-evidence")
    if args.production and args.output is None:
        parser.error("--production requires --output to persist transaction evidence")
    if args.migrate_power_flag_instance_flags and args.output is None:
        parser.error("--migrate-power-flag-instance-flags requires --output")
    if args.record_visual_approval:
        if not args.candidate_evidence or not args.output or not args.approved_by or not args.visual_checklist:
            parser.error("--record-visual-approval requires --candidate-evidence, --output, --approved-by, and --visual-checklist")
        checklist = json.loads(args.visual_checklist.read_text())
        result = record_visual_approval(args.candidate_evidence, args.output, args.approved_by, checklist)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    schematic = SCHEMATIC if (args.production or args.preflight or args.migrate_power_flag_instance_flags) else None
    with McpClient(KONNECT, CONFIG) as client:
        if args.production:
            result = run_production_transaction(
                client, SCHEMATIC, args.candidate_evidence, args.output
            )
        elif args.preflight:
            result = preflight(client, SCHEMATIC)
        elif args.migrate_power_flag_instance_flags:
            result = migrate_power_flag_instance_flags(client, SCHEMATIC, args.output)
        else:
            if schematic is None:
                directory = args.candidate_dir or Path(tempfile.mkdtemp(prefix="lh60-debug-sch."))
                directory.mkdir(parents=True, exist_ok=True)
                schematic = candidate(client, directory)
            svg_output = Path(tempfile.mkdtemp(prefix="lh60-sch-svg.")) / "lh60.svg"
            data = _query(client, schematic, svg_output)
            result = {
                "mode": "production" if args.production else "candidate",
                "schematic": str(schematic),
                "plan_hash": _plan_hash(),
                "git_sha": _git_sha(),
                **acceptance_record(data),
                "queries": data,
            }
            if args.render:
                result["render_sha256"] = hashlib.sha256(args.render.read_bytes()).hexdigest()
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
