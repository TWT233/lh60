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
    for toolset in ("sch_components", "sch_analysis", "sch_export", "sch_batch"):
        client.tool_schemas(toolset)


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


def preflight(client: McpClient, schematic: Path) -> dict[str, Any]:
    _load_acceptance_toolsets(client)
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    if {key: layout.get(key) for key in EXPECTED_BASELINE} != EXPECTED_BASELINE:
        raise AssertionError(f"production baseline mismatch: {layout}")
    wires = client.call_tool_json("list_schematic_wires", {"schematic": str(schematic)})["wires"]
    labels = client.call_tool_json("list_schematic_labels", {"schematic": str(schematic)})["labels"]
    wire_uuids = assert_unique_nonempty_uuids(wires, "wire")
    label_uuids = assert_unique_nonempty_uuids(labels, "label")
    refs = [item["reference"] for item in client.call_tool_json("list_schematic_components", {"schematic": str(schematic)})["components"]]
    expected_tp = {f"TP{index}" for index in range(1, 24)}
    if {ref for ref in refs if ref.startswith("TP")} != expected_tp:
        raise AssertionError("production TestPoint inventory mismatch")
    return {"layout": layout, "wire_uuids": wire_uuids, "label_uuids": label_uuids, "references": refs}


def converge(client: McpClient, schematic: Path, state: dict[str, Any]) -> None:
    require_schematic_capabilities(client)
    client.call_tool("batch_delete_schematic_wire", {"schematic": str(schematic), "uuids": state["wire_uuids"]})
    client.call_tool("batch_delete", {"schematic": str(schematic), "uuids": state["label_uuids"]})
    client.call_tool("batch_delete_schematic_components", {"schematic": str(schematic), "references": state["references"]})
    layout = client.call_tool_json("get_schematic_layout", {"schematic": str(schematic)})
    if any(layout.get(key) != 0 for key in ("component_count", "wire_count", "label_count")):
        raise AssertionError(f"convergence delete did not empty schematic: {layout}")
    apply_schematic(client, schematic)


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
    args = parser.parse_args()
    schematic = SCHEMATIC if args.production or args.preflight else None
    with McpClient(KONNECT, CONFIG) as client:
        if args.preflight:
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
                "acceptance": _assert_acceptance(data),
                "svg_path": data["svg_path"],
                "svg_sha256": hashlib.sha256(Path(data["svg_path"]).read_bytes()).hexdigest(),
                "queries": data,
            }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
