from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tools.lh60_design.interconnect import PIN_COUNT, interboard_contract
from tools.lh60_design.mcp import McpClient
from tools.lh60_design.pcb import (
    PASSIVE_CONNECTOR_FOOTPRINT,
    PASSIVE_CONNECTOR_REFERENCE,
    PASSIVE_CONNECTOR_VALUE,
    PASSIVE_LEGACY_REMOVALS,
    apply_passive_ffc_placement,
    audit_passive_ffc_candidates,
    passive_board_references,
    passive_connector_pad_nets,
    selected_passive_ffc_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMATIC = ROOT / "lh60.kicad_sch"
BOARD = ROOT / "lh60.kicad_pcb"
EXPECTED_SCHEMATIC_HASH = "de6ee0b579280c4950ca3264246698cccfeab4eb2e4a03f6755534a24b23a33e"
EXPECTED_BOARD_HASH = "eb27463ebcb973e44b5aea551c79ac4470615a3a7f0519a4b1c54c2afd466a46"
SCHEMA_VERSION = 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha() -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()


def require_production_unchanged(
    schematic: Path = SCHEMATIC,
    board: Path = BOARD,
) -> dict[str, str]:
    hashes = {"schematic": sha256(schematic), "board": sha256(board)}
    if hashes["schematic"] != EXPECTED_SCHEMATIC_HASH:
        raise RuntimeError(f"protected schematic hash mismatch: {hashes['schematic']}")
    if hashes["board"] != EXPECTED_BOARD_HASH:
        raise RuntimeError(f"protected PCB hash mismatch: {hashes['board']}")
    return hashes


def require_passive_capabilities(client: McpClient) -> None:
    expected = {
        "sch_export": {
            "update_pcb_from_schematic": {
                "required": {"schematic", "board"},
                "properties": {"schematic", "board", "dry_run", "expected_plan_revision"},
            },
        },
        "pcb_components": {
            "get_component_list": {"required": {"board"}, "properties": {"board"}},
            "get_component_pads": {
                "required": {"board", "reference"},
                "properties": {"board", "reference"},
            },
            "delete_component": {
                "required": {"board", "reference"},
                "properties": {"board", "reference"},
            },
            "flip_component": {
                "required": {"board", "reference", "layer"},
                "properties": {"board", "reference", "layer"},
            },
            "set_component_placements": {
                "required": {"board", "placements"},
                "properties": {"board", "placements"},
            },
        },
        "verification": {
            "run_drc": {
                "required": {"board"},
                "properties": {"board", "limit", "severity"},
            },
        },
        "pcb_export": {
            "export_svg": {
                "required": {"board", "output"},
                "properties": {"board", "output", "layers", "black_and_white"},
            },
        },
        "project": {
            "save_project": {"required": set(), "properties": set()},
        },
    }
    for toolset, tools in expected.items():
        schemas = client.tool_schemas(toolset)
        for name, contract in tools.items():
            schema = schemas.get(name)
            if schema is None:
                raise RuntimeError(f"missing Konnect tool: {name}")
            required = schema.get("required", [])
            if set(required) != contract["required"]:
                raise RuntimeError(f"{name} required inputs mismatch: {required}")
            missing = contract["properties"] - set(schema.get("properties", {}))
            if missing:
                raise RuntimeError(f"{name} missing input properties: {sorted(missing)}")


def candidate_audits_payload() -> list[dict[str, Any]]:
    payload = []
    for audit in audit_passive_ffc_candidates():
        placement = audit.placement
        payload.append(
            {
                "reference": placement.reference,
                "x": placement.x_mm,
                "y": placement.y_mm,
                "rotation": placement.rotation_deg,
                "layer": placement.layer,
                "mouth_edge": placement.mouth_edge,
                "mouth_direction": placement.mouth_direction,
                "stiffener_insertion_mm": placement.stiffener_insertion_mm,
                "first_bend_clearance_mm": placement.first_bend_clearance_mm,
                "copper_to_edge_mm": placement.copper_to_edge_mm,
                "body_envelope": vars(placement.body_envelope()),
                "courtyard_envelope": vars(placement.courtyard_envelope()),
                "access_envelope": vars(placement.access_envelope()),
                "viable": audit.viable,
                "rejection_reasons": list(audit.rejection_reasons),
            }
        )
    return payload


def copy_candidate_project(candidate_dir: Path) -> tuple[Path, Path, Path]:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for relative in (
        "lh60.kicad_pro",
        "lh60.kicad_sch",
        "lh60.kicad_pcb",
        "fp-lib-table",
        "sym-lib-table",
    ):
        shutil.copy2(ROOT / relative, candidate_dir / relative)
    library_src = ROOT / "lib"
    if library_src.exists():
        shutil.copytree(library_src, candidate_dir / "lib", dirs_exist_ok=True)
    return (
        candidate_dir / "lh60.kicad_sch",
        candidate_dir / "lh60.kicad_pcb",
        candidate_dir / "lh60.kicad_pro",
    )


def existing_candidate_project(candidate_dir: Path) -> tuple[Path, Path, Path]:
    paths = (
        candidate_dir / "lh60.kicad_sch",
        candidate_dir / "lh60.kicad_pcb",
        candidate_dir / "lh60.kicad_pro",
    )
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"existing candidate project is incomplete: {missing}")
    return paths


def _component_inventory(client: McpClient, board: Path) -> dict[str, Any]:
    result = client.call_tool_json("get_component_list", {"board": str(board.resolve())})
    components = result.get("components")
    if not isinstance(components, list):
        raise RuntimeError("get_component_list returned no components")
    if result.get("count") != len(components):
        raise RuntimeError("get_component_list count mismatch")
    references = []
    items = []
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("reference"), str):
            raise RuntimeError("component entry missing reference")
        reference = component["reference"]
        references.append(reference)
        items.append(
            {
                "reference": reference,
                "value": str(component.get("value", "")),
                "footprint": str(component.get("footprint", "")),
                "layer": str(component.get("layer", "")),
                "x": component.get("x"),
                "y": component.get("y"),
                "rotation": component.get("rotation"),
            }
        )
    duplicates = sorted(ref for ref in set(references) if references.count(ref) > 1)
    if duplicates:
        raise RuntimeError(f"duplicate component references: {duplicates}")
    return {
        "count": len(items),
        "references": sorted(references),
        "items": sorted(items, key=lambda item: item["reference"]),
    }


def require_passive_inventory(client: McpClient, board: Path, label: str) -> dict[str, Any]:
    inventory = _component_inventory(client, board)
    actual = set(inventory["references"])
    expected = set(passive_board_references())
    if actual != expected:
        raise RuntimeError(
            f"{label} passive inventory mismatch: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    if actual & set(PASSIVE_LEGACY_REMOVALS):
        raise RuntimeError(f"{label} still contains legacy active-board references")
    j1 = next(item for item in inventory["items"] if item["reference"] == PASSIVE_CONNECTOR_REFERENCE)
    if j1["value"] != PASSIVE_CONNECTOR_VALUE:
        raise RuntimeError("J1 value mismatch")
    if j1["footprint"] != PASSIVE_CONNECTOR_FOOTPRINT:
        raise RuntimeError("J1 footprint mismatch")
    return inventory


def _logical_net_name(board_net: Any, label: str) -> str | None:
    if board_net in {None, "", "~"}:
        return None
    if not isinstance(board_net, str):
        raise RuntimeError(f"{label} net must be a string")
    logical = board_net[1:] if board_net.startswith("/") else board_net
    if "/" in logical:
        raise RuntimeError(f"{label} unexpected hierarchical net: {board_net}")
    return logical


def _j1_pad_net_name(board_net: Any, number: str) -> str | None:
    if number == "23" and board_net == "unconnected-(J1-Pad23)":
        return None
    logical = _logical_net_name(board_net, f"J1 pad {number}")
    if isinstance(board_net, str) and board_net.startswith("unconnected-"):
        raise RuntimeError(f"J1 pad {number} unexpected unconnected sentinel: {board_net}")
    return logical


def _pad_layers(pad: dict[str, Any]) -> set[str]:
    layers = pad.get("layers")
    if isinstance(layers, list):
        return {str(layer) for layer in layers}
    if isinstance(layers, str):
        return {layers}
    layer = pad.get("layer")
    if isinstance(layer, str) and layer:
        return {layer}
    return set()


def _is_unconnected_mechanical_net(board_net: Any) -> bool:
    return (
        board_net in {None, "", "~"}
        or (isinstance(board_net, str) and board_net.startswith("unconnected-"))
    )


def require_passive_connector_pads(client: McpClient, board: Path) -> dict[str, Any]:
    expected = passive_connector_pad_nets()
    result = client.call_tool_json(
        "get_component_pads",
        {"board": str(board.resolve()), "reference": PASSIVE_CONNECTOR_REFERENCE},
    )
    pads = result.get("pads")
    if result.get("reference") != PASSIVE_CONNECTOR_REFERENCE or not isinstance(pads, list):
        raise RuntimeError("J1 pad response mismatch")
    if result.get("pad_count") != 26 or len(pads) != 26:
        raise RuntimeError("J1 physical pad count mismatch")
    electrical_pads = [pad for pad in pads if str(pad.get("number") or "")]
    mechanical_pads = [pad for pad in pads if not str(pad.get("number") or "")]
    if len(electrical_pads) != PIN_COUNT:
        raise RuntimeError("J1 electrical pad count mismatch")
    if len(mechanical_pads) != 2:
        raise RuntimeError("J1 mechanical land count mismatch")
    actual: dict[str, str | None] = {}
    normalized = []
    for pad in electrical_pads:
        if not isinstance(pad, dict):
            raise RuntimeError("J1 pad entry malformed")
        number = str(pad.get("number"))
        if number in actual:
            raise RuntimeError(f"J1 duplicate electrical pad number: {number}")
        actual[number] = _j1_pad_net_name(pad.get("net"), number)
        normalized.append(
            {
                "number": number,
                "net": actual[number],
                "board_net": pad.get("net"),
                "layers": sorted(_pad_layers(pad)),
                "x": pad.get("x"),
                "y": pad.get("y"),
            }
        )
    expected_numbers = {str(index) for index in range(1, PIN_COUNT + 1)}
    if set(actual) != expected_numbers:
        raise RuntimeError(f"J1 electrical pad numbers mismatch: {sorted(actual)}")
    mechanical = []
    for pad in mechanical_pads:
        if not isinstance(pad, dict):
            raise RuntimeError("J1 mechanical land entry malformed")
        if not _is_unconnected_mechanical_net(pad.get("net")):
            raise RuntimeError(f"J1 mechanical land unexpectedly connected: {pad.get('net')}")
        layers = _pad_layers(pad)
        if layers and layers != {"B.Cu", "B.Mask", "B.Paste"}:
            raise RuntimeError(f"J1 mechanical land layers mismatch: {sorted(layers)}")
        x = pad.get("x")
        y = pad.get("y")
        if x is not None and not isinstance(x, (int, float)):
            raise RuntimeError("J1 mechanical land x coordinate must be numeric when present")
        if y is not None and not isinstance(y, (int, float)):
            raise RuntimeError("J1 mechanical land y coordinate must be numeric when present")
        mechanical.append(
            {
                "number": "",
                "net": None,
                "board_net": pad.get("net"),
                "layers": sorted(layers),
                "x": x,
                "y": y,
            }
        )
    expected_with_nc = {str(pin.number): pin.net_name for pin in interboard_contract().pins}
    if actual != expected_with_nc:
        raise RuntimeError(f"J1 pad-net mismatch: {actual}")
    if set(expected) != set(actual) - {"23"}:
        raise RuntimeError("J1 connected pad set mismatch")
    return {
        "reference": PASSIVE_CONNECTOR_REFERENCE,
        "physical_pad_count": 26,
        "electrical_pad_count": PIN_COUNT,
        "mechanical_land_count": 2,
        "connected_pad_nets": expected,
        "pads": sorted(normalized, key=lambda item: int(item["number"])),
        "mechanical_lands": sorted(
            mechanical,
            key=lambda item: (
                float(item["x"]) if isinstance(item["x"], (int, float)) else 0.0,
                float(item["y"]) if isinstance(item["y"], (int, float)) else 0.0,
            ),
        ),
    }


def validate_sync_plan(payload: dict[str, Any], *, expected_status: str) -> dict[str, Any]:
    if payload.get("status") != expected_status:
        raise RuntimeError(f"sync status mismatch: expected {expected_status}")
    if not isinstance(payload.get("plan_revision"), str) or not payload["plan_revision"]:
        raise RuntimeError("sync plan_revision missing")
    diagnostics = payload.get("diagnostics")
    if diagnostics not in ([], None):
        raise RuntimeError(f"sync diagnostics are not empty: {diagnostics}")
    return payload


def _reference_identity_conflicts(payload: dict[str, Any]) -> list[str]:
    if payload.get("status") != "conflict":
        return []
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, list) or not diagnostics:
        return []
    references = []
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            return []
        if diagnostic.get("code") != "reference_identity_conflict":
            return []
        reference = diagnostic.get("reference")
        if not isinstance(reference, str) or not reference:
            return []
        references.append(reference)
    return sorted(set(references))


def _preserved_matrix_placements(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    matrix_refs = passive_board_references() - {PASSIVE_CONNECTOR_REFERENCE}
    preserved = []
    for item in inventory["items"]:
        if item["reference"] not in matrix_refs:
            continue
        preserved.append(
            {
                "reference": item["reference"],
                "x": item["x"],
                "y": item["y"],
                "rotation": item["rotation"],
            }
        )
    if len(preserved) != len(matrix_refs):
        raise RuntimeError("cannot preserve complete matrix placement set")
    return sorted(preserved, key=lambda item: item["reference"])


def _restore_matrix_placements(
    client: McpClient,
    board: Path,
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    result = client.call_tool_json(
        "set_component_placements",
        {"board": str(board.resolve()), "placements": placements},
    )
    result_placements = result.get("placements")
    if not isinstance(result_placements, list) or len(result_placements) != len(placements):
        raise RuntimeError("matrix placement restoration evidence mismatch")
    return result


def _export_svg(client: McpClient, board: Path, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = client.call_tool_json(
        "export_svg",
        {
            "board": str(board.resolve()),
            "output": str(output),
            "layers": ["B.Cu", "B.Fab", "B.CrtYd", "Edge.Cuts"],
        },
    )
    if not output.is_file():
        candidate = result.get("output") or result.get("path")
        if isinstance(candidate, str) and Path(candidate).is_file():
            output = Path(candidate)
        else:
            raise RuntimeError("back SVG export did not create an output file")
    return {"path": str(output), "sha256": sha256(output), "tool_result": result}


def _run_drc(client: McpClient, board: Path) -> dict[str, Any]:
    result = client.call_tool_json(
        "run_drc",
        {"board": str(board.resolve()), "limit": 10000, "severity": "info"},
    )
    if result.get("truncated") is not False:
        raise RuntimeError("DRC evidence is truncated")
    if result.get("severity_filter") != "info":
        raise RuntimeError("DRC evidence must be info severity")
    if result.get("schematic_parity", 0) != 0:
        raise RuntimeError("candidate has schematic parity DRC violations")
    return result


def _write_report(report: Path, result: dict[str, Any]) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def _load_phase_evidence(path: Path, *, expected_phase: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"{expected_phase} requires live-sync evidence: {path}")
    payload = json.loads(path.read_text())
    if payload.get("phase") != expected_phase:
        raise RuntimeError(f"expected prior phase {expected_phase}, got {payload.get('phase')}")
    return payload


def _require_prior_candidate_hash(prior: dict[str, Any], candidate_board: Path) -> str:
    expected = prior.get("candidate", {}).get("board_hash_after")
    if not isinstance(expected, str) or not expected:
        raise RuntimeError("prior phase evidence missing candidate board_hash_after")
    actual = sha256(candidate_board)
    if actual != expected:
        raise RuntimeError(
            f"candidate board hash mismatch: expected prior {expected}, got {actual}"
        )
    return actual


def _phase_base(
    *,
    phase: str,
    production_hashes: dict[str, str],
    after_production_hashes: dict[str, str],
    candidate_dir: Path,
    candidate_schematic: Path,
    candidate_board: Path,
    before_candidate_hash: str,
    schematic: Path,
    board: Path,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "candidate",
        "phase": phase,
        "status": "NEEDS_CONTEXT",
        "git_sha": git_sha(),
        "production": {
            "schematic": str(schematic.resolve()),
            "board": str(board.resolve()),
            "hashes_before": production_hashes,
            "hashes_after": after_production_hashes,
            "unchanged": production_hashes == after_production_hashes,
        },
        "candidate": {
            "directory": str(candidate_dir.resolve()),
            "schematic": str(candidate_schematic.resolve()),
            "board": str(candidate_board.resolve()),
            "board_hash_before": before_candidate_hash,
            "board_hash_after": sha256(candidate_board),
        },
    }


def run_live_sync_phase(
    client: McpClient,
    *,
    candidate_dir: Path,
    report: Path,
    schematic: Path = SCHEMATIC,
    board: Path = BOARD,
    use_existing_candidate: bool = False,
) -> dict[str, Any]:
    production_hashes = require_production_unchanged(schematic, board)
    require_passive_capabilities(client)
    if use_existing_candidate:
        candidate_schematic, candidate_board, _candidate_project = existing_candidate_project(candidate_dir)
    else:
        candidate_schematic, candidate_board, _candidate_project = copy_candidate_project(candidate_dir)
    before_candidate_hash = sha256(candidate_board)
    before_inventory = _component_inventory(client, candidate_board)

    sync_args = {
        "schematic": str(candidate_schematic.resolve()),
        "board": str(candidate_board.resolve()),
    }
    first_dry_run = client.call_tool_json(
        "update_pcb_from_schematic",
        {**sync_args, "dry_run": True},
    )
    identity_conflicts = _reference_identity_conflicts(first_dry_run)
    deleted_refs: list[dict[str, Any]] = []
    restored_matrix: dict[str, Any] | None = None
    preserved_matrix = _preserved_matrix_placements(before_inventory)
    if identity_conflicts:
        allowed_delete_refs = set(passive_board_references()) | set(PASSIVE_LEGACY_REMOVALS)
        if set(identity_conflicts) - allowed_delete_refs:
            raise RuntimeError(f"unexpected identity conflicts: {identity_conflicts}")
        for reference in before_inventory["references"]:
            if reference not in allowed_delete_refs:
                raise RuntimeError(f"candidate contains unexpected non-passive reference: {reference}")
            deleted_refs.append(
                client.call_tool_json(
                    "delete_component",
                    {"board": str(candidate_board.resolve()), "reference": reference},
                )
            )
        dry_run = validate_sync_plan(
            client.call_tool_json(
                "update_pcb_from_schematic",
                {**sync_args, "dry_run": True},
            ),
            expected_status="ready",
        )
    else:
        dry_run = validate_sync_plan(first_dry_run, expected_status="ready")

    apply_result = validate_sync_plan(
        client.call_tool_json(
            "update_pcb_from_schematic",
            {
                **sync_args,
                "dry_run": False,
                "expected_plan_revision": dry_run["plan_revision"],
            },
        ),
        expected_status="applied",
    )
    if apply_result["plan_revision"] != dry_run["plan_revision"]:
        raise RuntimeError("apply plan_revision differs from dry run")

    if identity_conflicts:
        restored_matrix = _restore_matrix_placements(client, candidate_board, preserved_matrix)
    client.call_tool("save_project", {})
    inventory = _component_inventory(client, candidate_board)
    after_production_hashes = require_production_unchanged(schematic, board)
    result = _phase_base(
        phase="live-sync",
        production_hashes=production_hashes,
        after_production_hashes=after_production_hashes,
        candidate_dir=candidate_dir,
        candidate_schematic=candidate_schematic,
        candidate_board=candidate_board,
        before_candidate_hash=before_candidate_hash,
        schematic=schematic,
        board=board,
    )
    result.update(
        {
            "next_action": "close PCB editor on this candidate, then run phase closed-pose",
            "bounded_search": {
                "audits": candidate_audits_payload(),
                "selected": vars(selected_passive_ffc_candidate()),
            },
            "sync": {
                "first_dry_run": first_dry_run,
                "identity_conflicts": identity_conflicts,
                "deleted_refs": deleted_refs,
                "dry_run": dry_run,
                "apply": apply_result,
                "restored_matrix_placements": restored_matrix,
            },
            "inventory_after_sync": inventory,
            "approval": {
                "required_before_production_mutation": True,
                "status": "missing",
            },
        }
    )
    _write_report(report, result)
    return result


def run_closed_pose_phase(
    client: McpClient,
    *,
    candidate_dir: Path,
    report: Path,
    prior_report: Path,
    schematic: Path = SCHEMATIC,
    board: Path = BOARD,
) -> dict[str, Any]:
    production_hashes = require_production_unchanged(schematic, board)
    require_passive_capabilities(client)
    candidate_schematic, candidate_board, _candidate_project = existing_candidate_project(candidate_dir)
    prior = _load_phase_evidence(prior_report, expected_phase="live-sync")
    before_candidate_hash = _require_prior_candidate_hash(prior, candidate_board)
    try:
        placement = apply_passive_ffc_placement(client, candidate_board)
    except RuntimeError as error:
        if "KiCAD currently holds this board open" in str(error):
            raise RuntimeError(
                "closed-pose phase requires PCB editor closed for the candidate board"
            ) from error
        raise
    after_production_hashes = require_production_unchanged(schematic, board)
    result = _phase_base(
        phase="closed-pose",
        production_hashes=production_hashes,
        after_production_hashes=after_production_hashes,
        candidate_dir=candidate_dir,
        candidate_schematic=candidate_schematic,
        candidate_board=candidate_board,
        before_candidate_hash=before_candidate_hash,
        schematic=schematic,
        board=board,
    )
    result.update(
        {
            "prior_phase": {"path": str(prior_report.resolve()), "phase": "live-sync"},
            "next_action": "reopen this same candidate in PCB editor, then run phase live-verify",
            "bounded_search": {
                "audits": candidate_audits_payload(),
                "selected": vars(selected_passive_ffc_candidate()),
            },
            "placement": list(placement),
            "approval": {
                "required_before_production_mutation": True,
                "status": "missing",
            },
        }
    )
    _write_report(report, result)
    return result


def _require_final_pose(inventory: dict[str, Any]) -> dict[str, Any]:
    placement = selected_passive_ffc_candidate()
    j1 = next(item for item in inventory["items"] if item["reference"] == PASSIVE_CONNECTOR_REFERENCE)
    expected = {
        "layer": placement.layer,
        "x": placement.x_mm,
        "y": placement.y_mm,
        "rotation": placement.rotation_deg,
    }
    for field, value in expected.items():
        actual = j1.get(field)
        if field == "layer":
            if actual != value:
                raise RuntimeError(f"J1 layer mismatch: expected {value}, got {actual}")
        elif not isinstance(actual, (int, float)) or abs(float(actual) - float(value)) > 0.01:
            raise RuntimeError(f"J1 {field} mismatch: expected {value}, got {actual}")
    return {**j1, "access_envelope": vars(placement.access_envelope())}


def _export_layer_svg(
    client: McpClient,
    board: Path,
    output: Path,
    *,
    layers: list[str],
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = client.call_tool_json(
        "export_svg",
        {
            "board": str(board.resolve()),
            "output": str(output),
            "layers": layers,
            "black_and_white": False,
        },
    )
    if not output.is_file():
        candidate = result.get("output") or result.get("path")
        if isinstance(candidate, str) and Path(candidate).is_file():
            output = Path(candidate)
        else:
            raise RuntimeError(f"SVG export did not create {output}")
    return {"path": str(output), "sha256": sha256(output), "tool_result": result}


def _render_3d(board: Path, output: Path, *, side: str, kicad_cli: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(kicad_cli),
        "pcb",
        "render",
        "--side",
        side,
        "--output",
        str(output),
        str(board.resolve()),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"3D render {side} failed with exit {completed.returncode}: {completed.stderr.strip()}"
        )
    if not output.is_file():
        raise RuntimeError(f"3D render did not create {output}")
    return {"path": str(output), "sha256": sha256(output), "command": command}


def run_live_verify_phase(
    client: McpClient,
    *,
    candidate_dir: Path,
    report: Path,
    prior_report: Path,
    schematic: Path = SCHEMATIC,
    board: Path = BOARD,
    kicad_cli: Path = Path("/data00/home/wangqiyilang/.local/bin/kicad-cli"),
) -> dict[str, Any]:
    production_hashes = require_production_unchanged(schematic, board)
    require_passive_capabilities(client)
    candidate_schematic, candidate_board, _candidate_project = existing_candidate_project(candidate_dir)
    prior = _load_phase_evidence(prior_report, expected_phase="closed-pose")
    before_candidate_hash = _require_prior_candidate_hash(prior, candidate_board)
    inventory = require_passive_inventory(client, candidate_board, "candidate")
    pose = _require_final_pose(inventory)
    pads = require_passive_connector_pads(client, candidate_board)
    drc = _run_drc(client, candidate_board)
    front_svg = _export_layer_svg(
        client,
        candidate_board,
        candidate_dir / "candidate-front.svg",
        layers=["F.Cu", "F.Fab", "F.CrtYd", "Edge.Cuts"],
    )
    back_svg = _export_layer_svg(
        client,
        candidate_board,
        candidate_dir / "candidate-back.svg",
        layers=["B.Cu", "B.Fab", "B.CrtYd", "Edge.Cuts"],
    )
    renders = {
        "front": _render_3d(
            candidate_board,
            candidate_dir / "candidate-front-3d.png",
            side="front",
            kicad_cli=kicad_cli,
        ),
        "back": _render_3d(
            candidate_board,
            candidate_dir / "candidate-back-3d.png",
            side="back",
            kicad_cli=kicad_cli,
        ),
    }
    client.call_tool("save_project", {})
    readback_hash = sha256(candidate_board)
    after_production_hashes = require_production_unchanged(schematic, board)
    result = _phase_base(
        phase="live-verify",
        production_hashes=production_hashes,
        after_production_hashes=after_production_hashes,
        candidate_dir=candidate_dir,
        candidate_schematic=candidate_schematic,
        candidate_board=candidate_board,
        before_candidate_hash=before_candidate_hash,
        schematic=schematic,
        board=board,
    )
    result.update(
        {
            "status": "CANDIDATE_READY_FOR_APPROVAL",
            "prior_phase": {"path": str(prior_report.resolve()), "phase": "closed-pose"},
            "candidate": {
                **result["candidate"],
                "board_hash_after_save_readback": readback_hash,
                "front_svg": front_svg,
                "back_svg": back_svg,
                "renders_3d": renders,
            },
            "sync": {"final_noop": "skipped: controller requested no resync during phase C resume"},
            "inventory": inventory,
            "pads": pads,
            "pose": pose,
            "drc": drc,
            "approval": {
                "required_before_production_mutation": True,
                "status": "candidate_ready",
            },
        }
    )
    _write_report(report, result)
    return result


def generate_candidate(
    client: McpClient,
    *,
    candidate_dir: Path,
    report: Path,
    schematic: Path = SCHEMATIC,
    board: Path = BOARD,
    use_existing_candidate: bool = False,
) -> dict[str, Any]:
    return run_live_sync_phase(
        client,
        candidate_dir=candidate_dir,
        report=report,
        schematic=schematic,
        board=board,
        use_existing_candidate=use_existing_candidate,
    )


def load_approval(path: Path) -> dict[str, Any]:
    approval = json.loads(path.read_text())
    if approval.get("approved") is not True:
        raise RuntimeError("production apply requires approved=true")
    for field in ("candidate_board_sha256", "candidate_svg_sha256", "approved_by"):
        if not isinstance(approval.get(field), str) or not approval[field].strip():
            raise RuntimeError(f"production approval missing {field}")
    return approval


def apply_production_requires_approval(approval_path: Path | None) -> None:
    if approval_path is None:
        raise RuntimeError("production apply is blocked until an approval artifact is supplied")
    load_approval(approval_path)
    raise RuntimeError("production mutation intentionally not implemented in Task 2 candidate gate")


def default_candidate_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="lh60-passive-main-pcb-candidate."))
