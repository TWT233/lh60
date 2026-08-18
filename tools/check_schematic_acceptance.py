from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
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


ROOT = Path(__file__).resolve().parents[1]
KONNECT = Path("/data00/home/wangqiyilang/.local/bin/konnect")
CONFIG = Path.home() / ".config/konnect/config.toml"
EXPECTED_BASELINE = {"component_count": 172, "wire_count": 290, "label_count": 339}
EXPECTED_INVENTORY = {"mcu": 1, "switch": 75, "diode": 70, "connector": 6, "flag": 3}
EXPECTED_PRODUCTION_TESTPOINTS = {f"TP{index}" for index in range(1, 24)}
EXPECTED_PRODUCTION_REFERENCES = (
    {"U1", *{f"J{index}" for index in range(1, 7)}, *{f"#FLG{index:02d}" for index in range(1, 4)}}
    | {f"D{index}" for index in range(1, 71)}
    | {f"SW{index}" for index in range(1, 77) if index != 59}
    | EXPECTED_PRODUCTION_TESTPOINTS
)


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
        for toolset in ("sch_components", "sch_analysis", "sch_export", "sch_batch")
    }
    contracts = {
        "list_schematic_components": ("sch_components", ("schematic",)),
        "get_schematic_layout": ("sch_components", ("schematic",)),
        "list_schematic_wires": ("sch_components", ("schematic",)),
        "list_schematic_labels": ("sch_components", ("schematic",)),
        "export_netlist_summary": ("sch_analysis", ("schematic",)),
        "check_schematic_overlaps": ("sch_analysis", ("schematic",)),
        "find_orphan_items": ("sch_analysis", ("schematic",)),
        "find_shorted_nets": ("sch_analysis", ("schematic",)),
        "find_single_pin_nets": ("sch_analysis", ("schematic",)),
        "validate_wire_connections": ("sch_analysis", ("schematic",)),
        "validate_component_connections": ("sch_analysis", ("schematic",)),
        "get_pin_net_name": ("sch_analysis", ("schematic", "reference", "pin_number")),
        "run_erc": ("sch_analysis", ("schematic", "severity")),
        "export_schematic_svg": ("sch_export", ("schematic", "output")),
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


def preflight(client: McpClient, schematic: Path) -> dict[str, Any]:
    _load_acceptance_toolsets(client)
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    wires = client.call_tool_json("list_schematic_wires", {"schematic": str(schematic)})["wires"]
    labels = client.call_tool_json("list_schematic_labels", {"schematic": str(schematic)})["labels"]
    wire_uuids = assert_unique_nonempty_uuids(wires, "wire")
    label_uuids = assert_unique_nonempty_uuids(labels, "label")
    refs = [item["reference"] for item in client.call_tool_json("list_schematic_components", {"schematic": str(schematic)})["components"]]
    state = {"layout": layout, "wire_uuids": wire_uuids, "label_uuids": label_uuids, "references": refs}
    assert_production_preflight(state, set(refs))
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
) -> dict[str, Any]:
    """Execute the one-way production transaction only after bound review evidence."""
    evidence_file = _evidence_path(candidate_evidence_path)
    candidate_evidence = json.loads(evidence_file.read_text())
    expected_plan_hash = expected_plan_hash or _plan_hash()
    expected_git_sha = expected_git_sha or _git_sha()
    candidate_fn = candidate_fn or candidate
    assert_candidate_evidence(candidate_evidence, expected_plan_hash, expected_git_sha)
    capabilities_fn(client)

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


def candidate(client: McpClient, directory: Path) -> Path:
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
    args = parser.parse_args()
    if args.production and args.preflight:
        parser.error("--production and --preflight are mutually exclusive")
    if args.production and args.candidate_evidence is None:
        parser.error("--production requires --candidate-evidence")
    if args.production and args.output is None:
        parser.error("--production requires --output to persist transaction evidence")
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
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
