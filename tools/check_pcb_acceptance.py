from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from tools.lh60_design.mcp import McpClient
from tools.lh60_design.pcb import BOARD, frozen_connector_placements
from tools.verify_pcb_sync import CONNECTOR_PAD_NETS, final_board_refs


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KICAD_CLI = Path.home() / ".local/bin/kicad-cli"
KICAD_CLI = DEFAULT_KICAD_CLI
EXPECTED_DRC_TOTAL = 530
EXPECTED_DRC_UNCONNECTED = 367
EXPECTED_DRC_FOOTPRINT = 163
EXPECTED_DRC_ERRORS = 457
EXPECTED_DRC_WARNINGS = 73
EXPECTED_CONNECTOR_GRAPHICS = {"B.Fab": 1, "B.CrtYd": 1, "B.SilkS": 6}
FORBIDDEN_FRONT_GRAPHICS = {"F.Fab": 0, "F.CrtYd": 0, "F.SilkS": 0}
CONNECTOR_REFERENCES = tuple(CONNECTOR_PAD_NETS)
EXPECTED_CONNECTOR_UNCONNECTED_ENDPOINTS = tuple(
    (reference, pad_number, net)
    for reference, pads in CONNECTOR_PAD_NETS.items()
    for pad_number, net in pads.items()
)
DRC_SECTION_RE = re.compile(r"^\[([^]]+)\]:")
CONNECTOR_ENDPOINT_RE = re.compile(
    r"\bPTH pad (?P<pad_number>\S+) "
    r"\[(?P<net>[^]]+)\] of (?P<reference>J\d+)\b"
)
CONNECTOR_ITEM_RE = re.compile(r"\bof J\d+\b")
DRC_ITEM_LINE_RE = re.compile(r"^@\([^)]*\):\s+(?P<description>.+)$")
DRC_ITEM_REFERENCE_RE = re.compile(
    r"^(?:Footprint (?P<footprint_reference>\S+)|"
    r".+\bof (?P<owned_reference>\S+?)(?: on \S+)?)$"
)
CONNECTOR_REFERENCE_RE = re.compile(r"^J\d+$")


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def resolve_kicad_cli(cli: Path | None = None) -> Path:
    if cli is not None:
        return cli
    if DEFAULT_KICAD_CLI.exists():
        return DEFAULT_KICAD_CLI
    return Path("kicad-cli")


def _require_contract(
    schemas: dict[str, dict[str, Any]],
    tool: str,
    required_inputs: tuple[str, ...],
    properties: tuple[str, ...],
) -> None:
    schema = schemas.get(tool)
    if schema is None:
        raise RuntimeError(f"Konnect PCB acceptance capability mismatch: missing {tool}")
    actual_required = sorted(schema.get("required", []))
    if actual_required != sorted(required_inputs):
        raise RuntimeError(
            f"Konnect PCB acceptance capability mismatch: {tool} required inputs differ: "
            f"expected={sorted(required_inputs)}, actual={actual_required}"
        )
    missing = sorted(set(properties) - set(schema.get("properties", {})))
    if missing:
        raise RuntimeError(f"Konnect PCB acceptance capability mismatch: {tool} missing {missing}")


def require_pcb_acceptance_capabilities(client: McpClient) -> None:
    contracts = {
        "pcb_components": {
            "get_component_list": (("board",), ("board",)),
            "get_component_pads": (("board", "reference"), ("board", "reference")),
            "list_board_footprint_graphics": (("board", "reference"), ("board", "reference", "layer")),
        },
        "verification": {
            "run_drc": (("board",), ("board", "limit", "severity")),
        },
        "pcb_export": {
            "export_position_file": (
                ("board", "output"),
                ("board", "output", "format", "units", "side"),
            ),
        },
    }
    for toolset, tool_contracts in contracts.items():
        load_result = client.call_tool_json("load_toolset", {"name": toolset})
        if load_result.get("loaded") != toolset:
            raise RuntimeError(
                f"Konnect PCB acceptance capability mismatch: failed to load {toolset}"
            )
        owned_names = {
            item.get("name")
            for item in load_result.get("tools", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        missing_owned = sorted(set(tool_contracts) - owned_names)
        if missing_owned:
            raise RuntimeError(
                f"Konnect PCB acceptance capability mismatch: {toolset} does not own {missing_owned}"
            )
        listed = client.request("tools/list", {}).get("tools")
        if not isinstance(listed, list):
            raise RuntimeError("Konnect PCB acceptance capability mismatch: tools/list malformed")
        schemas = {
            tool["name"]: tool.get("inputSchema", {})
            for tool in listed
            if isinstance(tool, dict) and tool.get("name") in owned_names
        }
        for tool, (required_inputs, properties) in tool_contracts.items():
            _require_contract(schemas, tool, required_inputs, properties)


def _require_exact_inventory(client: McpClient, board: Path) -> dict[str, Any]:
    result = client.call_tool_json("get_component_list", {"board": str(board.resolve())})
    components = result.get("components")
    if not isinstance(components, list):
        raise RuntimeError("get_component_list returned no components list")
    if result.get("count") != len(components):
        raise RuntimeError("get_component_list count mismatch")
    references = [
        item.get("reference")
        for item in components
        if isinstance(item, dict) and isinstance(item.get("reference"), str)
    ]
    if len(references) != len(components):
        raise RuntimeError("get_component_list contains malformed component reference")
    duplicate_refs = sorted(
        reference for reference, count in Counter(references).items() if count != 1
    )
    if duplicate_refs:
        raise RuntimeError(f"duplicate component reference: {duplicate_refs}")
    actual_refs = set(references)
    expected_refs = final_board_refs()
    if actual_refs != expected_refs:
        missing = sorted(expected_refs - actual_refs)
        extra = sorted(actual_refs - expected_refs)
        raise RuntimeError(f"final 152 references mismatch: missing={missing}, extra={extra}")
    normalized = {item["reference"]: item for item in components}
    return {"count": len(components), "references": sorted(actual_refs), "items": normalized}


def _graphics_by_layer(graphics: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for graphic in graphics:
        by_layer.setdefault(str(graphic.get("layer")), []).append(graphic)
    return by_layer


def _require_connector_pose_and_graphics(client: McpClient, board: Path) -> dict[str, Any]:
    inventory = _require_exact_inventory(client, board)["items"]
    evidence = {}
    for placement in frozen_connector_placements():
        component = inventory[placement.reference]
        if component.get("layer") != "B.Cu":
            raise RuntimeError(f"{placement.reference} layer mismatch: expected B.Cu")
        for field, expected in (("x", placement.x_mm), ("y", placement.y_mm), ("rotation", placement.rotation_deg)):
            actual = component.get(field)
            if actual != expected:
                raise RuntimeError(
                    f"{placement.reference} {field} mismatch: expected {expected}, got {actual}"
                )
        layer_counts = {}
        for layer in (*EXPECTED_CONNECTOR_GRAPHICS, *FORBIDDEN_FRONT_GRAPHICS):
            result = client.call_tool_json(
                "list_board_footprint_graphics",
                {"board": str(board.resolve()), "reference": placement.reference, "layer": layer},
            )
            graphics = result.get("graphics")
            if not isinstance(graphics, list):
                raise RuntimeError(f"{placement.reference} {layer} graphics payload malformed")
            layer_counts[layer] = len(graphics)
        for layer, expected in EXPECTED_CONNECTOR_GRAPHICS.items():
            if layer_counts[layer] != expected:
                raise RuntimeError(
                    f"{placement.reference} {layer} graphic count mismatch: expected {expected}, got {layer_counts[layer]}"
                )
        for layer, expected in FORBIDDEN_FRONT_GRAPHICS.items():
            if layer_counts[layer] != expected:
                raise RuntimeError(
                    f"{placement.reference} {layer} graphic count mismatch: expected {expected}, got {layer_counts[layer]}"
                )
        evidence[placement.reference] = {
            "x": placement.x_mm,
            "y": placement.y_mm,
            "rotation": placement.rotation_deg,
            "layer": "B.Cu",
            "graphics": layer_counts,
        }
    return evidence


def _logical_net_name(board_net: Any, label: str) -> str:
    if not isinstance(board_net, str) or not board_net:
        raise RuntimeError(f"{label} board net must be a nonempty string")
    return board_net.rsplit("/", 1)[-1]


def _require_connector_pad_nets(client: McpClient, board: Path) -> dict[str, Any]:
    pads_by_reference = {}
    total = 0
    for reference, expected in CONNECTOR_PAD_NETS.items():
        result = client.call_tool_json(
            "get_component_pads",
            {"board": str(board.resolve()), "reference": reference},
        )
        pads = result.get("pads")
        if not isinstance(pads, list) or result.get("pad_count") != len(pads):
            raise RuntimeError(f"{reference} pad payload/count mismatch")
        actual = {}
        for pad in pads:
            if not isinstance(pad, dict) or not isinstance(pad.get("number"), str):
                raise RuntimeError(f"{reference} pad payload malformed")
            actual[pad["number"]] = _logical_net_name(pad.get("net"), f"{reference} pad {pad.get('number')}")
        if actual != expected:
            raise RuntimeError(f"{reference} pad-net mismatch: expected {expected}, got {actual}")
        pads_by_reference[reference] = actual
        total += len(actual)
    if total != 23:
        raise RuntimeError(f"connector pad-net coverage mismatch: expected 23, got {total}")
    return pads_by_reference


def _normalize_drc_entry(entry: dict[str, Any]) -> dict[str, Any]:
    pos = entry.get("pos")
    if not isinstance(pos, dict):
        pos = {}
    return {
        "rule": str(entry.get("rule", "")),
        "description": str(entry.get("description", "")),
        "severity": str(entry.get("severity", "")),
        "pos": {
            "x": pos.get("x"),
            "y": pos.get("y"),
        },
    }


def _parse_drc_report(report_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_rule: str | None = None
    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section = DRC_SECTION_RE.match(line)
        if section is not None:
            current_rule = section.group(1)
            sections.setdefault(current_rule, [])
            continue
        if current_rule is not None:
            sections[current_rule].append(line)
    return sections


def _require_exact_connector_unconnected_endpoints(
    report_text: str,
) -> list[dict[str, str]]:
    unconnected_lines = _parse_drc_report(report_text).get("unconnected_items", [])
    endpoints = []
    unparsed_connector_lines = []
    for line in unconnected_lines:
        match = CONNECTOR_ENDPOINT_RE.search(line)
        if match is not None:
            endpoints.append(
                (
                    match.group("reference"),
                    match.group("pad_number"),
                    match.group("net").removeprefix("/"),
                )
            )
        elif CONNECTOR_ITEM_RE.search(line):
            unparsed_connector_lines.append(line)

    counts = Counter(endpoints)
    expected = set(EXPECTED_CONNECTOR_UNCONNECTED_ENDPOINTS)
    missing = [
        endpoint
        for endpoint in EXPECTED_CONNECTOR_UNCONNECTED_ENDPOINTS
        if counts[endpoint] == 0
    ]
    duplicate = [
        endpoint
        for endpoint in EXPECTED_CONNECTOR_UNCONNECTED_ENDPOINTS
        if counts[endpoint] > 1
    ]
    unexpected = sorted(endpoint for endpoint in counts if endpoint not in expected)
    if missing or duplicate or unexpected or unparsed_connector_lines:
        raise RuntimeError(
            "connector unconnected endpoints mismatch: "
            f"missing={missing}, duplicate={duplicate}, unexpected={unexpected}, "
            f"unparsed={unparsed_connector_lines}"
        )
    endpoint_order = {
        endpoint: index
        for index, endpoint in enumerate(EXPECTED_CONNECTOR_UNCONNECTED_ENDPOINTS)
    }
    return [
        {"reference": reference, "pad_number": pad_number, "net": net}
        for reference, pad_number, net in sorted(
            endpoints,
            key=endpoint_order.__getitem__,
        )
    ]


def _drc_item_reference(line: str) -> str | None:
    item = DRC_ITEM_LINE_RE.match(line)
    if item is None:
        return None
    reference = DRC_ITEM_REFERENCE_RE.match(item.group("description"))
    if reference is None:
        return None
    return reference.group("footprint_reference") or reference.group("owned_reference")


def _check_report_for_unexpected_connector_findings(report_text: str) -> list[dict[str, Any]]:
    findings = []
    for rule, lines in _parse_drc_report(report_text).items():
        if rule == "unconnected_items":
            continue
        for line in lines:
            reference = _drc_item_reference(line)
            if reference is not None and CONNECTOR_REFERENCE_RE.fullmatch(reference):
                findings.append({"rule": rule, "line": line})
    return findings


def _write_drc_report(board: Path, output_dir: Path, *, kicad_cli: Path) -> dict[str, Any]:
    report = output_dir / "drc.rpt"
    if report.exists():
        raise RuntimeError(f"DRC report output already exists: {report}")
    command = [
        str(kicad_cli),
        "pcb",
        "drc",
        "--format",
        "report",
        "--units",
        "mm",
        "--severity-all",
        "--output",
        str(report),
        str(board.resolve()),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    if not report.is_file():
        raise RuntimeError(f"DRC report missing: {report}")
    report_text = report.read_text()
    if not report_text.strip():
        raise RuntimeError(f"DRC report empty: {report}")
    return {
        "path": str(report),
        "sha256": hashlib.sha256(report_text.encode()).hexdigest(),
        "text": report_text,
        "command": command,
    }


def _require_drc(client: McpClient, board: Path, output_dir: Path, *, kicad_cli: Path) -> dict[str, Any]:
    result = client.call_tool_json(
        "run_drc",
        {"board": str(board.resolve()), "limit": 10000, "severity": "info"},
    )
    for field, expected in (
        ("total_violations", EXPECTED_DRC_TOTAL),
        ("unconnected_items", EXPECTED_DRC_UNCONNECTED),
        ("schematic_parity", 0),
    ):
        if result.get(field) != expected:
            raise RuntimeError(f"DRC {field} mismatch: expected {expected}, got {result.get(field)}")
    if result.get("design_rule_violations") != EXPECTED_DRC_FOOTPRINT:
        raise RuntimeError("DRC design_rule_violations mismatch")
    if result.get("errors") != EXPECTED_DRC_ERRORS or result.get("warnings") != EXPECTED_DRC_WARNINGS:
        raise RuntimeError("DRC errors/warnings mismatch")
    if result.get("truncated") is not False or result.get("severity_filter") != "info":
        raise RuntimeError("DRC report is not a full info report")
    violations = result.get("violations")
    if not isinstance(violations, list):
        raise RuntimeError("DRC violations payload malformed")
    normalized = [_normalize_drc_entry(entry) for entry in violations if isinstance(entry, dict)]
    report = _write_drc_report(board, output_dir, kicad_cli=kicad_cli)
    unexpected = _check_report_for_unexpected_connector_findings(report["text"])
    if unexpected:
        raise RuntimeError(f"unexpected J-related DRC report finding: {unexpected}")
    connector_endpoints = _require_exact_connector_unconnected_endpoints(report["text"])
    return {
        "total_violations": result["total_violations"],
        "unconnected_items": result["unconnected_items"],
        "schematic_parity": result["schematic_parity"],
        "design_rule_violations": result["design_rule_violations"],
        "errors": result["errors"],
        "warnings": result["warnings"],
        "violations": normalized,
        "connector_unconnected_endpoints": connector_endpoints,
        "report_path": report["path"],
        "report_sha256": report["sha256"],
        "report_command": report["command"],
    }


def _require_position_export_without_connectors(client: McpClient, board: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"position output already exists: {output}")
    client.call_tool(
        "export_position_file",
        {
            "board": str(board.resolve()),
            "output": str(output),
            "format": "csv",
            "units": "mm",
            "side": "both",
        },
    )
    with output.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "Ref" not in reader.fieldnames:
            raise RuntimeError("position export must contain Ref column")
        rows = list(reader)
    for row in rows:
        reference = row.get("Ref", "")
        if reference in CONNECTOR_REFERENCES:
            raise RuntimeError(f"position export must exclude {reference}")
    return {
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "rows": len(rows),
    }


def _export_back_svg(board: Path, output: Path, *, kicad_cli: Path) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"back SVG output already exists: {output}")
    command = [
        str(kicad_cli),
        "pcb",
        "export",
        "svg",
        "--output",
        str(output),
        "--layers",
        "B.SilkS,B.Fab,B.CrtYd,Edge.Cuts",
        "--mode-single",
        "--mirror",
        "--exclude-drawing-sheet",
        "--fit-page-to-board",
        "--page-size-mode",
        "2",
        str(board.resolve()),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    if not output.is_file():
        raise RuntimeError(f"back SVG export missing: {output}")
    return {
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "command": command,
    }


def acceptance_record(
    client: McpClient,
    board: Path,
    *,
    output_dir: Path,
    kicad_cli: Path | None = None,
) -> dict[str, Any]:
    board_hash_before = hashlib.sha256(board.read_bytes()).hexdigest()
    require_pcb_acceptance_capabilities(client)
    output_dir.mkdir(parents=True, exist_ok=True)
    for output in (output_dir / "drc.rpt", output_dir / "positions.csv", output_dir / "back.svg"):
        if output.exists():
            raise RuntimeError(f"acceptance output already exists: {output}")
    resolved_kicad_cli = resolve_kicad_cli(kicad_cli)
    pose = _require_connector_pose_and_graphics(client, board)
    pads = _require_connector_pad_nets(client, board)
    drc = _require_drc(client, board, output_dir, kicad_cli=resolved_kicad_cli)
    positions = _require_position_export_without_connectors(
        client, board, output_dir / "positions.csv"
    )
    svg = _export_back_svg(board, output_dir / "back.svg", kicad_cli=resolved_kicad_cli)
    board_hash_after = hashlib.sha256(board.read_bytes()).hexdigest()
    if board_hash_after != board_hash_before:
        raise RuntimeError(
            "board changed during acceptance: "
            f"before={board_hash_before}, after={board_hash_after}"
        )
    return {
        "git_sha": _git_sha(),
        "board": str(board.resolve()),
        "board_sha256": board_hash_before,
        "board_integrity": {
            "sha256_before": board_hash_before,
            "sha256_after": board_hash_after,
            "equal": board_hash_before == board_hash_after,
        },
        "coverage": {
            "expected_refs": 152,
            "connector_pad_nets": 23,
            "connector_graphic_layers": {
                **EXPECTED_CONNECTOR_GRAPHICS,
                **FORBIDDEN_FRONT_GRAPHICS,
            },
        },
        "connectors": pose,
        "pad_nets": pads,
        "drc": drc,
        "positions": positions,
        "back_svg": svg,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live PCB acceptance for LH60 production board.")
    parser.add_argument("--board", type=Path, default=BOARD)
    parser.add_argument("--konnect", type=Path, default=Path.home() / ".local/bin/konnect")
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/konnect/config.toml")
    parser.add_argument("--kicad-cli", type=Path, default=resolve_kicad_cli())
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/lh60-pcb-acceptance"))
    parser.add_argument("--production", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with McpClient(args.konnect, args.config) as client:
        evidence = acceptance_record(client, args.board, output_dir=args.output_dir, kicad_cli=args.kicad_cli)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
