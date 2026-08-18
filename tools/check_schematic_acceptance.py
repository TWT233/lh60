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
    SCHEMATIC,
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
VISUAL_CHECKLIST = {"u1", "matrix", "connectors", "title_block"}


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
        "list_schematic_components": ("sch_components", ("schematic",)),
        "get_schematic_layout": ("sch_batch", ("schematic",)),
        "validate_wire_connections": ("sch_batch", ("schematic",)),
        "validate_component_connections": ("sch_batch", ("schematic",)),
        "batch_delete_schematic_wire": ("sch_wiring", ("schematic", "uuids")),
        "export_netlist_summary": ("sch_export", ("schematic",)),
        "run_erc": ("sch_export", ("schematic", "severity")),
        "export_schematic_svg": ("sch_export", ("schematic", "output")),
        "list_schematic_wires": ("sch_analysis", ("schematic",)),
        "list_schematic_labels": ("sch_analysis", ("schematic",)),
        "check_schematic_overlaps": ("sch_analysis", ("schematic",)),
        "find_orphan_items": ("sch_analysis", ("schematic",)),
        "find_shorted_nets": ("sch_analysis", ("schematic",)),
        "find_single_pin_nets": ("sch_analysis", ("schematic",)),
        "get_pin_net_name": ("sch_analysis", ("schematic", "reference", "pin_number")),
    }
    missing = {}
    for tool, (toolset, inputs) in contracts.items():
        schema = schemas[toolset].get(tool)
        if schema is None:
            missing[tool] = ["tool"]
            continue
        absent = sorted(
            set(inputs) - set(schema.get("required", []))
        )
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
    semantic_nets: dict[str, list[dict[str, str]]] = {}
    for connection in build_schematic_plan().connections:
        result = client.call_tool_json(
            "get_pin_net_name",
            {
                "schematic": str(schematic),
                "reference": connection.reference,
                "pin_number": connection.pin_number,
            },
        )
        net_name = result.get("net_name")
        if not net_name:
            raise AssertionError(
                f"missing net for {connection.reference}.{connection.pin_number}"
            )
        semantic_nets.setdefault(str(net_name), []).append(
            {"reference": connection.reference, "pin_number": connection.pin_number}
        )
    data["semantic"] = {"nets": [
        {"name": net_name, "pins": pins}
        for net_name, pins in sorted(semantic_nets.items())
    ]}
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


def frozen_plan_expectations() -> dict[str, Any]:
    """Independent, serializable acceptance baseline frozen at review time."""
    plan = build_schematic_plan()
    components = sorted(
        [
            {
                "reference": component.reference,
                "lib_id": component.lib_id,
                "value": component.value,
                "footprint": component.footprint,
            }
            for component in plan.components
        ],
        key=lambda item: item["reference"],
    )
    pins_by_net: dict[str, list[dict[str, str]]] = {}
    for connection in plan.connections:
        pins_by_net.setdefault(connection.net_name, []).append(
            {"reference": connection.reference, "pin_number": connection.pin_number}
        )
    semantic = normalize_net_semantics({
        "nets": [
            {"name": name, "pins": pins}
            for name, pins in pins_by_net.items()
        ]
    })
    connector_map = {
        group.reference: tuple(group.pin_map)
        for group in CONNECTOR_GROUPS
    }
    frozen_pins = sorted(
        [
            {"reference": connection.reference, "pin_number": connection.pin_number, "net_name": connection.net_name}
            for connection in plan.connections
        ],
        key=lambda item: (item["net_name"], item["reference"], int(item["pin_number"])),
    )
    if _stable_hash(components) != FROZEN_COMPONENT_SHA256 or _stable_hash(frozen_pins) != FROZEN_PIN_SHA256:
        raise AssertionError("frozen plan baseline drift")
    return {"components": components, "semantic": semantic, "connector_map": connector_map}


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list).encode()
    ).hexdigest()


def assert_frozen_acceptance(data: dict[str, Any], frozen: dict[str, Any] | None = None) -> None:
    """Check live candidate/production facts against the reviewed plan."""
    frozen = frozen or frozen_plan_expectations()
    components = sorted(
        [
            {key: component.get(key, "") for key in ("reference", "lib_id", "value", "footprint")}
            for component in data["components"]["components"]
        ],
        key=lambda item: item["reference"],
    )
    if components != frozen["components"]:
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
    actual_semantic = normalize_net_semantics(data["semantic"])
    if actual_semantic != frozen["semantic"]:
        raise AssertionError("pin semantic contract mismatch")
    expected_assignments = sum(len(pins) for pins in frozen["semantic"].values())
    if sum(len(pins) for pins in actual_semantic.values()) != expected_assignments:
        raise AssertionError("pin assignment count mismatch")
    for reference, pin_map in frozen["connector_map"].items():
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
    _write_json(output_path, approval)
    return approval


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


def _writer_pids(path: Path) -> list[str]:
    result = subprocess.run(
        ["lsof", "-t", "--", str(path)],
        text=True, capture_output=True, check=False,
    )
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


def prepare_candidate_libraries(
    client_factory, project_dir: Path, *, apply_core_fn=apply_core_library, apply_mcu_fn=apply_mcu_library,
    capability_fn=require_schematic_capabilities,
) -> dict[str, list[str]]:
    """Regenerate with isolated clients, then query the actual candidate assets."""
    with client_factory(KONNECT, CONFIG) as client:
        capability_fn(client)
        apply_core_fn(client)
    with client_factory(KONNECT, CONFIG) as client:
        capability_fn(client)
        apply_mcu_fn(client)
    symbols = ("Conn_01x03", "Conn_01x04", "Conn_01x05", "RP2040-Tiny")
    footprints = (
        "PinHeader_1x03_P2.54mm_Vertical",
        "PinHeader_1x04_P2.54mm_Vertical",
        "PinHeader_1x05_P2.54mm_Vertical",
        "MCU_RP2040-Tiny_SMD",
    )
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
                {"footprint_path": str(root / f"{name}.kicad_mod"), "include_graphics": True, "project": str(project_dir)},
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
        candidate_schematic = candidate_fn(client, output_directory / "candidate")
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


def candidate(client: McpClient, directory: Path, *, prepare_libraries_fn=prepare_candidate_libraries) -> Path:
    if prepare_libraries_fn is not None:
        prepare_libraries_fn(McpClient, directory)
    client.call_tool("create_project", {"path": str(directory), "name": "lh60-candidate"})
    project = directory / "lh60-candidate.kicad_pro"
    client.tool_schemas("library")
    registrations = candidate_library_registrations(str(project))
    for registration in registrations["symbols"]:
        client.call_tool("register_symbol_library", {**registration, "scope": "project", "replace_existing": True})
    for registration in registrations["footprints"]:
        client.call_tool("register_footprint_library", {**registration, "scope": "project", "replace_existing": True})
    schematic = directory / "lh60-candidate.kicad_sch"
    apply_schematic(client, schematic)
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
    if args.production and args.preflight:
        parser.error("--production and --preflight are mutually exclusive")
    if args.production and args.candidate_evidence is None:
        parser.error("--production requires --candidate-evidence")
    if args.production and args.output is None:
        parser.error("--production requires --output to persist transaction evidence")
    if args.record_visual_approval:
        if not args.candidate_evidence or not args.output or not args.approved_by or not args.visual_checklist:
            parser.error("--record-visual-approval requires --candidate-evidence, --output, --approved-by, and --visual-checklist")
        checklist = json.loads(args.visual_checklist.read_text())
        result = record_visual_approval(args.candidate_evidence, args.output, args.approved_by, checklist)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    schematic = SCHEMATIC if args.production or args.preflight else None
    with McpClient(KONNECT, CONFIG) as client:
        if args.production:
            result = run_production_transaction(
                client, SCHEMATIC, args.candidate_evidence, args.output
            )
        elif args.preflight:
            result = preflight(client, SCHEMATIC)
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
