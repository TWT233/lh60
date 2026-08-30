import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tools.lh60_design.interconnect import interboard_contract
from tools.lh60_design.mcp import McpClient
from tools.lh60_design.pcb import (
    PASSIVE_CONNECTOR_FOOTPRINT,
    PASSIVE_CONNECTOR_VALUE,
    PASSIVE_LEGACY_REMOVALS,
    apply_passive_ffc_placement,
    audit_passive_ffc_candidates,
    passive_board_references,
    passive_connector_pad_nets as design_passive_connector_pad_nets,
    selected_passive_ffc_candidate,
)


def schema(required, *properties):
    return {
        "required": list(required),
        "properties": {name: {} for name in properties},
    }


def complete_pcb_sync_schemas():
    return {
        "pcb_components": {
            "get_component_list": schema(("board",), "board"),
            "get_component_pads": schema(("board", "reference"), "board", "reference"),
            "delete_component": schema(("board", "reference"), "board", "reference"),
            "flip_component": schema(
                ("board", "reference", "layer"), "board", "reference", "layer"
            ),
            "set_component_placements": schema(
                ("board", "placements"),
                "board",
                "placements",
            ),
            "list_board_footprint_graphics": schema(
                ("board", "reference"), "board", "reference", "layer"
            ),
        },
        "pcb_board": {
            "get_board_info": schema(("board",), "board"),
        },
        "sch_export": {
            "update_pcb_from_schematic": schema(
                ("schematic", "board"),
                "schematic",
                "board",
                "dry_run",
                "expected_plan_revision",
            ),
        },
        "verification": {
            "launch_kicad_ui": schema(
                (),
                "project",
                "timeout_seconds",
                "wait_ready",
            ),
            "run_drc": schema(("board",), "board", "limit", "severity"),
        },
        "pcb_export": {
            "export_svg": schema(("board", "output"), "board", "output", "layers", "black_and_white"),
        },
        "project": {
            "save_project": {"required": [], "properties": {}},
        },
    }


def text_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def raw_text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def empty_result():
    return {"content": []}


def matrix_refs():
    refs = set()
    refs.update({f"D{index}" for index in range(1, 71)})
    refs.update({f"SW{index}" for index in range(1, 59)})
    refs.update({f"SW{index}" for index in range(60, 77)})
    return refs


def old_board_refs():
    return matrix_refs() | {"U1", "J1", "J2", "J3", "J4", "J5", "J6"}


def final_board_refs():
    return matrix_refs() | {"J1"}


def passive_connector_pad_nets():
    return {
        str(pin.number): pin.net_name
        for pin in interboard_contract().pins
        if pin.net_name is not None
    }


def component_list_payload(references, *, connector_positions=None):
    connector_positions = {} if connector_positions is None else connector_positions
    components = [
            {
                "reference": reference,
                "value": CONNECTOR_VALUES.get(reference, f"value-{reference}"),
                "footprint": CONNECTOR_FOOTPRINTS.get(
                    reference, f"library:{reference}"
                ),
                "layer": "F.Cu",
                "x": (
                    connector_positions[reference][0]
                    if reference in connector_positions
                    else float(index)
                ),
                "y": (
                    connector_positions[reference][1]
                    if reference in connector_positions
                    else float(index) / 2.0
                ),
                "rotation": 0.0,
            }
            for index, reference in enumerate(sorted(references), start=1)
        ]
    return {"count": len(components), "components": components}


def board_info_payload(zone_count=0):
    return {
        "file": "/tmp/lh60.kicad_pcb",
        "title": "",
        "date": "",
        "revision": "",
        "company": "",
        "paper": "A4",
        "layer_count": 32,
        "copper_layer_count": 2,
        "net_count": 93,
        "zone_count": zone_count,
    }


def manufacturing_payload(track_count=0):
    return {
        "verdict": "NOT READY",
        "fab_house": "jlcpcb",
        "board_info": {
            "footprint_count": 169,
            "copper_layers": 2,
            "net_count": 93,
            "track_count": track_count,
        },
        "drc": {
            "errors": 0,
            "design_rule_violations": 0,
            "unconnected_items": 367,
            "schematic_parity": 0,
        },
        "issues": [],
        "summary": "NOT READY: intentionally unrouted board",
    }


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


def pad_payload(reference, *, hierarchical=True):
    index = int(reference.removeprefix("TP"))
    logical_net = TP_NETS[reference]
    return {
        "reference": reference,
        "pad_count": 1,
        "pads": [
            {
                "number": "1",
                "net": f"/{logical_net}" if hierarchical else logical_net,
                "x": 10.0 + index,
                "y": 20.0 + index,
            }
        ],
    }


def connector_pad_payload(reference, *, hierarchical=True):
    pads = [
            {
                "number": number,
                "net": f"/{net_name}" if hierarchical else net_name,
                "x": 100.0 + int(number),
                "y": 200.0 + int(number),
            }
            for number, net_name in CONNECTOR_PAD_NETS[reference].items()
        ]
    return {
        "reference": reference,
        "pad_count": len(pads),
        "pads": pads,
    }


def passive_ffc_pad_payload(*, mechanical_layers=None, pad23_net="unconnected-(J1-Pad23)"):
    mechanical_layers = (
        ["B.Cu", "B.Mask", "B.Paste"]
        if mechanical_layers is None
        else mechanical_layers
    )
    pads = []
    for pin in interboard_contract().pins:
        if pin.number == 23:
            net = pad23_net
        elif pin.net_name is None:
            net = None
        else:
            net = f"/{pin.net_name}"
        pads.append(
            {
                "number": str(pin.number),
                "net": net,
                "layers": ["B.Cu", "B.Mask", "B.Paste"],
                "x": 250.0 + pin.number,
                "y": 10.0,
            }
        )
    pads.extend(
        [
            {
                "number": "",
                "net": "",
                "layers": mechanical_layers,
                "x": 267.8,
                "y": 7.68,
            },
            {
                "number": "",
                "net": "unconnected-(J1-PadMP2)",
                "layers": mechanical_layers,
                "x": 284.2,
                "y": 7.68,
            },
        ]
    )
    return {"reference": "J1", "pad_count": 26, "pads": pads}


def empty_trace_payload(net_name):
    _ = net_name
    return {"count": 0, "traces": []}


def drc_payload(*, truncated=False, categories_not_reported=None):
    return {
        "total_violations": 0,
        "design_rule_violations": 0,
        "unconnected_items": 0,
        "schematic_parity": 0,
        "categories_not_reported": (
            [] if categories_not_reported is None else categories_not_reported
        ),
        "filtered_count": 0,
        "errors": 0,
        "warnings": 0,
        "severity_filter": "info",
        "shown": 0,
        "truncated": truncated,
        "violations": [],
    }


def drc_with_j1_violation(rule="shorting_items"):
    payload = drc_payload()
    payload.update(
        {
            "total_violations": 1,
            "design_rule_violations": 1,
            "errors": 1,
            "shown": 1,
            "filtered_count": 1,
            "violations": [
                {
                    "rule": rule,
                    "severity": "error",
                    "description": f"regression fixture for {rule}",
                    "items": [
                        {"description": "Pad 1 [/GND] of J1 on B.Cu"},
                        {"description": "PTH pad 1 [/KEY_13] of SW14"},
                    ],
                }
            ],
        }
    )
    return payload


def sync_change(reference, x, y):
    return {
        "kind": "add",
        "reference": reference,
        "value": CONNECTOR_VALUES[reference],
        "footprint_id": CONNECTOR_FOOTPRINTS[reference],
        "symbol_path": f"/sheet/{reference.lower()}",
        "dnp": False,
        "pad_nets": CONNECTOR_PAD_NETS[reference],
        "position": {"x": x, "y": y},
    }


def sync_plan_payload(
    *,
    status,
    revision,
    board_only_planned,
    board_only_applied,
    skipped_applied,
    added_applied,
    diagnostics=None,
    changes=None,
    undo=None,
):
    return {
        "status": status,
        "plan_revision": revision,
        "coverage": {
            "source": "saved_schematic_hierarchy",
            "hierarchy_files": 1,
            "transport": "live_kicad_ipc",
            "atomicity": "single_kicad_undo_commit",
            "footprints_added": {"planned": 0 if status == "noop" else 6, "applied": added_applied},
            "footprints_updated": {"planned": 0, "applied": 0},
            "pads_reassigned": {"planned": 0, "applied": 0},
            "board_only_preserved": {
                "planned": board_only_planned,
                "applied": board_only_applied,
            },
            "skipped_by_flag": {"planned": 3, "applied": skipped_applied},
            "conflicts": {"planned": 0, "applied": 0},
        },
        "changes": (
            changes
            if changes is not None
            else []
            if status == "noop"
            else [
                sync_change("J1", 310.0, 90.0),
                sync_change("J2", 310.0, 120.0),
                sync_change("J3", 310.0, 150.0),
                sync_change("J4", 340.0, 120.0),
                sync_change("J5", 340.0, 150.0),
                sync_change("J6", 340.0, 180.0),
            ]
        ),
        "diagnostics": [] if diagnostics is None else diagnostics,
        "undo": undo,
    }


def queue_capture_baseline_flow(client, *, drc=None):
    client.queue_json("get_component_list", component_list_payload(old_board_refs()))
    client.queue_json("get_board_info", board_info_payload())
    client.queue_json("validate_for_manufacturing", manufacturing_payload())
    for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
        client.queue_json("get_component_pads", pad_payload(reference))
    client.queue_json("get_component_list", component_list_payload(old_board_refs()))
    for net_name in TP_NETS.values():
        client.queue_json("query_traces", empty_trace_payload(f"/{net_name}"))
    client.queue_json("run_drc", drc_payload() if drc is None else drc)


def baseline_fixture(git_sha=None):
    from tools.sync_debug_connectors import BOARD, SCHEMATIC, _git_sha, capture_baseline

    if git_sha is None:
        git_sha = _git_sha()

    client = FakeClient()
    queue_capture_baseline_flow(client)
    with mock.patch("tools.sync_debug_connectors._git_sha", return_value=git_sha):
        return capture_baseline(client, SCHEMATIC, BOARD)


def queue_pre_delete_live_state(
    client,
    *,
    references=None,
    zone_count=0,
    track_count=0,
    trace_overrides=None,
):
    client.queue_json(
        "get_component_list",
        component_list_payload(old_board_refs() if references is None else references),
    )
    client.queue_json("get_board_info", board_info_payload(zone_count=zone_count))
    client.queue_json(
        "validate_for_manufacturing",
        manufacturing_payload(track_count=track_count),
    )
    for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
        client.queue_json("get_component_pads", pad_payload(reference))
    client.queue_json(
        "get_component_list",
        component_list_payload(old_board_refs() if references is None else references),
    )
    overrides = trace_overrides or {}
    for net_name in TP_NETS.values():
        board_net = f"/{net_name}"
        client.queue_json(
            "query_traces",
            overrides.get(net_name, overrides.get(board_net, empty_trace_payload(board_net))),
        )


def default_sync_changes():
    return [
        sync_change("J1", 310.0, 90.0),
        sync_change("J2", 310.0, 120.0),
        sync_change("J3", 310.0, 150.0),
        sync_change("J4", 340.0, 120.0),
        sync_change("J5", 340.0, 150.0),
        sync_change("J6", 340.0, 180.0),
    ]


def queue_sync_through_apply(
    client,
    *,
    delete_overrides=None,
    second_dry=None,
    apply=None,
    pre_save_references=None,
    pre_save_connector_positions=None,
):
    queue_pre_delete_live_state(client)
    queue_rebind_stage(client)
    client.queue_json(
        "update_pcb_from_schematic",
        sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
        ),
    )
    overrides = delete_overrides or {}
    for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
        client.queue_json(
            "delete_component",
            overrides.get(reference, {"deleted": reference}),
        )
    client.queue_json("get_component_list", component_list_payload(shared_refs()))
    client.queue_json(
        "update_pcb_from_schematic",
        second_dry
        or sync_plan_payload(
            status="ready",
            revision="rev-after",
            board_only_planned=0,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
        ),
        apply
        or sync_plan_payload(
            status="applied",
            revision="rev-after",
            board_only_planned=0,
            board_only_applied=0,
            skipped_applied=3,
            added_applied=6,
            undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
        ),
    )
    queue_pre_save_gates(
        client,
        references=pre_save_references,
        connector_positions=pre_save_connector_positions,
    )


class FakeClient:
    result_json = staticmethod(McpClient.result_json)
    call_tool_json = McpClient.call_tool_json

    def __init__(self, schemas=None):
        self.schemas = deepcopy(schemas or complete_pcb_sync_schemas())
        self.responses = defaultdict(list)
        self.calls = []

    def tool_schemas(self, toolset):
        self.calls.append(("load", toolset))
        return deepcopy(self.schemas[toolset])

    def request(self, method, arguments):
        self.calls.append((method, deepcopy(arguments)))
        if method != "tools/list" or arguments != {}:
            raise AssertionError((method, arguments))
        return {
            "tools": [
                {"name": name, "inputSchema": schema}
                for toolset in self.schemas.values()
                for name, schema in toolset.items()
            ]
        }

    def queue_json(self, name, *payloads):
        for payload in payloads:
            self.responses[name].append(text_result(payload))

    def queue_raw(self, name, *results):
        for result in results:
            self.responses[name].append(result)

    def call_tool(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if name == "load_toolset":
            toolset = arguments["name"]
            tools = [
                {"name": tool_name, "description": f"{toolset}:{tool_name}"}
                for tool_name in self.schemas[toolset]
            ]
            return text_result(
                {
                    "loaded": toolset,
                    "tools_added": len(tools),
                    "tools": tools,
                }
            )
        if not self.responses[name]:
            raise AssertionError(f"missing queued response for {name}")
        response = self.responses[name].pop(0)
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)


class ExactOwnershipClient:
    def __init__(self, schemas=None):
        self.schemas = deepcopy(schemas or complete_pcb_sync_schemas())
        self.loaded = {}

    result_json = staticmethod(McpClient.result_json)
    call_tool_json = McpClient.call_tool_json

    def call_tool(self, name, arguments):
        if name != "load_toolset":
            raise AssertionError(name)
        toolset = arguments["name"]
        tools = [
            {"name": tool_name, "description": f"{toolset}:{tool_name}"}
            for tool_name in self.schemas[toolset]
        ]
        self.loaded.update(self.schemas[toolset])
        return text_result(
            {
                "loaded": toolset,
                "tools_added": len(tools),
                "tools": tools,
            }
        )

    def request(self, method, arguments):
        if method != "tools/list" or arguments != {}:
            raise AssertionError((method, arguments))
        return {
            "tools": [
                {"name": name, "inputSchema": schema}
                for name, schema in self.loaded.items()
            ]
        }


class PassivePcbSyncTest(unittest.TestCase):
    def test_passive_reference_set_and_connector_contract_are_frozen(self):
        refs = passive_board_references()

        self.assertEqual(len(refs), 146)
        self.assertEqual(len([ref for ref in refs if ref.startswith("SW")]), 75)
        self.assertEqual(len([ref for ref in refs if ref.startswith("D")]), 70)
        self.assertIn("J1", refs)
        self.assertFalse(set(PASSIVE_LEGACY_REMOVALS) & refs)
        self.assertEqual(PASSIVE_CONNECTOR_VALUE, "FPC-05F-24PH20")
        self.assertEqual(PASSIVE_CONNECTOR_FOOTPRINT, "lh60-interconnect:FPC-05F-24PH20")
        self.assertEqual(
            design_passive_connector_pad_nets(),
            {
                str(pin.number): pin.net_name
                for pin in interboard_contract().pins
                if pin.net_name is not None
            },
        )
        self.assertNotIn("23", design_passive_connector_pad_nets())

    def test_bounded_candidate_search_fails_closed_when_access_envelopes_collide(self):
        audits = audit_passive_ffc_candidates()

        self.assertGreaterEqual(len(audits), 4)
        self.assertFalse(any(audit.viable for audit in audits))
        first = audits[0]
        self.assertEqual(first.placement.x_mm, 276.0)
        self.assertEqual(first.placement.y_mm, 7.0)
        self.assertFalse(first.viable)
        self.assertTrue(
            any(reason.startswith("courtyard_collision_SW") for reason in first.rejection_reasons),
            first.rejection_reasons,
        )
        self.assertTrue(
            any(reason.startswith("access_collision_SW") for reason in first.rejection_reasons),
            first.rejection_reasons,
        )
        top_edge = audits[1]
        self.assertEqual(top_edge.placement.mouth_edge, "top")
        self.assertEqual(top_edge.placement.mouth_direction, "north")
        self.assertEqual(top_edge.placement.stiffener_insertion_mm, 6.0)
        self.assertEqual(top_edge.placement.first_bend_clearance_mm, 6.0)
        self.assertEqual(top_edge.placement.copper_to_edge_mm, 0.5)
        envelope = top_edge.placement.access_envelope()
        self.assertGreaterEqual(envelope.min_x, 0.5)
        self.assertGreaterEqual(envelope.min_y, 0.5)
        self.assertLessEqual(envelope.max_x, 285.25)
        self.assertLessEqual(envelope.max_y, 94.75)
        with self.assertRaisesRegex(RuntimeError, "no passive FFC placement candidate"):
            selected_passive_ffc_candidate()

    def test_passive_candidate_audit_rejects_access_envelope_socket_collision(self):
        from tools.lh60_design.pcb import PassiveFfcPlacement

        candidate = PassiveFfcPlacement("J1", 28.575, 7.425, 0.0)

        audit = audit_passive_ffc_candidates((candidate,))[0]

        self.assertFalse(audit.viable)
        self.assertTrue(
            any(reason.startswith("access_collision_SW") for reason in audit.rejection_reasons),
            audit.rejection_reasons,
        )

    def test_passive_ffc_bcu_rotation_zero_uses_live_flipped_courtyard_geometry(self):
        from tools.lh60_design.pcb import PassiveFfcPlacement

        placement = PassiveFfcPlacement("J1", 276.0, 7.0, 0.0)

        self.assertEqual(placement.mouth_edge, "top")
        self.assertEqual(placement.mouth_direction, "north")
        courtyard = placement.courtyard_envelope()
        self.assertAlmostEqual(courtyard.min_x, 267.31, places=2)
        self.assertAlmostEqual(courtyard.max_x, 284.69, places=2)
        self.assertAlmostEqual(courtyard.min_y, 0.95, places=2)
        self.assertAlmostEqual(courtyard.max_y, 7.875, places=3)
        access = placement.access_envelope()
        self.assertEqual(access.min_y, 0.5)
        self.assertEqual(access.max_y, courtyard.max_y)

    def test_apply_passive_ffc_placement_fails_closed_without_viable_candidate(self):
        client = FakeClient()

        with self.assertRaisesRegex(RuntimeError, "no passive FFC placement candidate"):
            apply_passive_ffc_placement(client, Path("/tmp/candidate.kicad_pcb"))

        self.assertEqual(
            [call[0] for call in client.calls],
            ["load"],
        )

    def test_passive_candidate_generation_refuses_production_apply_without_approval(self):
        from tools.passive_pcb_sync import apply_production_requires_approval

        with self.assertRaisesRegex(RuntimeError, "approval artifact"):
            apply_production_requires_approval(None)

    def test_passive_candidate_capability_gate_matches_deployed_tool_names(self):
        from tools.passive_pcb_sync import require_passive_capabilities

        require_passive_capabilities(FakeClient())

        schemas = complete_pcb_sync_schemas()
        schemas["pcb_components"].pop("set_component_placements")
        with self.assertRaisesRegex(RuntimeError, "set_component_placements"):
            require_passive_capabilities(FakeClient(schemas))

    def test_passive_connector_pads_accept_26_physical_pads_and_j1_pad23_sentinel(self):
        from tools.passive_pcb_sync import require_passive_connector_pads

        client = FakeClient()
        client.queue_json("get_component_pads", passive_ffc_pad_payload())

        evidence = require_passive_connector_pads(client, Path("/tmp/candidate.kicad_pcb"))

        self.assertEqual(evidence["physical_pad_count"], 26)
        self.assertEqual(evidence["electrical_pad_count"], 24)
        self.assertEqual(evidence["mechanical_land_count"], 2)
        pad23 = next(pad for pad in evidence["pads"] if pad["number"] == "23")
        self.assertIsNone(pad23["net"])
        self.assertEqual(
            {tuple(land["layers"]) for land in evidence["mechanical_lands"]},
            {("B.Cu", "B.Mask", "B.Paste")},
        )

    def test_passive_connector_pads_reject_duplicate_electrical_numbers(self):
        from tools.passive_pcb_sync import require_passive_connector_pads

        payload = passive_ffc_pad_payload()
        payload["pads"][1]["number"] = "1"
        client = FakeClient()
        client.queue_json("get_component_pads", payload)

        with self.assertRaisesRegex(RuntimeError, "electrical pad count|duplicate"):
            require_passive_connector_pads(client, Path("/tmp/candidate.kicad_pcb"))

    def test_passive_connector_pads_reject_wrong_mechanical_layers(self):
        from tools.passive_pcb_sync import require_passive_connector_pads

        client = FakeClient()
        client.queue_json(
            "get_component_pads",
            passive_ffc_pad_payload(mechanical_layers=["F.Cu", "F.Mask", "F.Paste"]),
        )

        with self.assertRaisesRegex(RuntimeError, "mechanical land layers"):
            require_passive_connector_pads(client, Path("/tmp/candidate.kicad_pcb"))

    def test_drc_gate_rejects_j1_physical_violations(self):
        from tools.passive_pcb_sync import require_no_j1_physical_drc_violations

        for rule in (
            "shorting_items",
            "clearance",
            "hole_clearance",
            "courtyards_overlap",
            "pth_inside_courtyard",
            "npth_inside_courtyard",
            "solder_mask_bridge",
        ):
            with self.subTest(rule=rule):
                with self.assertRaisesRegex(RuntimeError, "J1 physical DRC violations"):
                    require_no_j1_physical_drc_violations(drc_with_j1_violation(rule))

    def test_drc_gate_allows_global_unconnected_items(self):
        from tools.passive_pcb_sync import require_no_j1_physical_drc_violations

        payload = drc_payload()
        payload.update(
            {
                "total_violations": 1,
                "unconnected_items": 1,
                "shown": 1,
                "filtered_count": 1,
                "violations": [
                    {
                        "rule": "unconnected_items",
                        "severity": "error",
                        "description": "Pad 1 of SW1 is unconnected",
                        "items": [{"description": "Pad 1 of SW1"}],
                    }
                ],
            }
        )

        evidence = require_no_j1_physical_drc_violations(payload)

        self.assertEqual(evidence["j1_physical_violation_count"], 0)

    def test_drc_gate_allows_unrelated_physical_violations(self):
        from tools.passive_pcb_sync import require_no_j1_physical_drc_violations

        payload = drc_payload()
        payload.update(
            {
                "total_violations": 2,
                "design_rule_violations": 2,
                "errors": 2,
                "shown": 2,
                "filtered_count": 2,
                "violations": [
                    {
                        "rule": "hole_clearance",
                        "severity": "error",
                        "description": "legacy keyboard mechanical hole clearance",
                        "items": [
                            {"description": "Pad 1 [/KEY_21] of D22 on F.Cu"},
                            {"description": "NPTH pad of SW71"},
                        ],
                    },
                    {
                        "rule": "courtyards_overlap",
                        "severity": "error",
                        "description": "legacy keyboard courtyard overlap",
                        "items": [
                            {"description": "Footprint SW10 on B.Cu"},
                            {"description": "Footprint D10 on F.Cu"},
                        ],
                    },
                ],
            }
        )

        evidence = require_no_j1_physical_drc_violations(payload)

        self.assertEqual(evidence["j1_physical_violation_count"], 0)

    def test_phase_b_refuses_without_phase_a_evidence(self):
        from tools.passive_pcb_sync import run_closed_pose_phase

        with TemporaryDirectory() as temporary:
            candidate_dir = Path(temporary)
            (candidate_dir / "lh60.kicad_sch").write_text("schematic\n")
            (candidate_dir / "lh60.kicad_pcb").write_text("board\n")
            (candidate_dir / "lh60.kicad_pro").write_text("project\n")

            with self.assertRaisesRegex(RuntimeError, "requires live-sync evidence"):
                run_closed_pose_phase(
                    FakeClient(),
                    candidate_dir=candidate_dir,
                    report=candidate_dir / "phase-b.json",
                    prior_report=candidate_dir / "phase-a.json",
                )

    def test_phase_b_refuses_when_candidate_hash_differs_from_phase_a(self):
        from tools.passive_pcb_sync import run_closed_pose_phase, sha256

        with TemporaryDirectory() as temporary:
            candidate_dir = Path(temporary)
            candidate_board = candidate_dir / "lh60.kicad_pcb"
            (candidate_dir / "lh60.kicad_sch").write_text("schematic\n")
            candidate_board.write_text("changed-board\n")
            (candidate_dir / "lh60.kicad_pro").write_text("project\n")
            phase_a = candidate_dir / "phase-a.json"
            phase_a.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": "live-sync",
                        "candidate": {
                            "board": str(candidate_board),
                            "board_hash_after": sha256(candidate_board) + "-stale",
                        },
                    }
                )
            )

            with self.assertRaisesRegex(RuntimeError, "candidate board hash mismatch"):
                run_closed_pose_phase(
                    FakeClient(),
                    candidate_dir=candidate_dir,
                    report=candidate_dir / "phase-b.json",
                    prior_report=phase_a,
                )

    def test_phase_b_fails_closed_before_flip_when_no_candidate_is_viable(self):
        from tools.passive_pcb_sync import run_closed_pose_phase, sha256

        with TemporaryDirectory() as temporary:
            candidate_dir = Path(temporary)
            candidate_board = candidate_dir / "lh60.kicad_pcb"
            (candidate_dir / "lh60.kicad_sch").write_text("schematic\n")
            candidate_board.write_text("board\n")
            (candidate_dir / "lh60.kicad_pro").write_text("project\n")
            phase_a = candidate_dir / "phase-a.json"
            phase_a.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase": "live-sync",
                        "candidate": {
                            "board": str(candidate_board),
                            "board_hash_after": sha256(candidate_board),
                        },
                    }
                )
            )
            client = FakeClient()

            with self.assertRaisesRegex(RuntimeError, "no passive FFC placement candidate"):
                run_closed_pose_phase(
                    client,
                    candidate_dir=candidate_dir,
                    report=candidate_dir / "phase-b.json",
                    prior_report=phase_a,
                )
            self.assertNotIn("flip_component", [call[0] for call in client.calls])

    def test_phase_a_stops_before_closed_board_pose(self):
        from tools.passive_pcb_sync import run_live_sync_phase

        with TemporaryDirectory() as temporary:
            candidate_dir = Path(temporary)
            board = candidate_dir / "prod.kicad_pcb"
            schematic = candidate_dir / "prod.kicad_sch"
            for filename in ("lh60.kicad_pro", "lh60.kicad_sch", "lh60.kicad_pcb"):
                (candidate_dir / filename).write_text(f"{filename}\n")
            board.write_text("production-board\n")
            schematic.write_text("production-schematic\n")
            client = FakeClient()
            conflicts = [
                {"code": "reference_identity_conflict", "reference": reference}
                for reference in sorted(old_board_refs())
            ]
            client.queue_json("get_component_list", component_list_payload(old_board_refs()))
            for reference in sorted(old_board_refs()):
                client.queue_json("delete_component", {"deleted": reference})
            client.queue_json(
                "update_pcb_from_schematic",
                sync_plan_payload(
                    status="conflict",
                    revision="rev-conflict",
                    board_only_planned=152,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    diagnostics=conflicts,
                ),
                sync_plan_payload(
                    status="ready",
                    revision="rev-ready",
                    board_only_planned=0,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                ),
                sync_plan_payload(
                    status="applied",
                    revision="rev-ready",
                    board_only_planned=0,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=146,
                ),
            )
            client.queue_json(
                "set_component_placements",
                {"placements": [{"reference": ref} for ref in sorted(matrix_refs())]},
            )
            client.queue_json("save_project", {"saved": True})
            client.queue_json("get_component_list", component_list_payload(final_board_refs()))
            with mock.patch("tools.passive_pcb_sync.require_production_unchanged", return_value={}):
                result = run_live_sync_phase(
                    client,
                    candidate_dir=candidate_dir,
                    report=candidate_dir / "phase-a.json",
                    schematic=schematic,
                    board=board,
                    use_existing_candidate=True,
                )

            self.assertEqual(result["phase"], "live-sync")
            self.assertEqual(result["status"], "NEEDS_CONTEXT")
            self.assertIn("no viable J1 pose", result["next_action"])
            self.assertEqual(result["bounded_search"]["status"], "no_viable_candidate")
            self.assertEqual(result["bounded_search"]["viable_count"], 0)
            self.assertIsNone(result["bounded_search"]["selected"])
            self.assertNotIn("flip_component", [call[0] for call in client.calls])


@unittest.skip("superseded six-debug-header sync tests retained for historical audit only")
class PcbSyncContractTest(unittest.TestCase):
    def setUp(self):
        import tools.sync_debug_connectors as pcb_sync

        schematic = pcb_sync.SCHEMATIC.resolve()
        board = pcb_sync.BOARD.resolve()

        def frozen_pre_sync_hash(path):
            resolved = Path(path).resolve()
            if resolved == schematic:
                return pcb_sync.EXPECTED_SCHEMATIC_HASH
            if resolved == board:
                return pcb_sync.EXPECTED_BOARD_HASH
            raise AssertionError(f"unexpected protected fixture path: {resolved}")

        hash_patcher = mock.patch.object(
            pcb_sync,
            "_sha256",
            side_effect=frozen_pre_sync_hash,
        )
        hash_patcher.start()
        self.addCleanup(hash_patcher.stop)

    def test_fake_client_hash_fixture_returns_frozen_pre_sync_hashes(self):
        import tools.sync_debug_connectors as pcb_sync

        self.assertEqual(pcb_sync._sha256(pcb_sync.BOARD), pcb_sync.EXPECTED_BOARD_HASH)
        self.assertEqual(
            pcb_sync._sha256(pcb_sync.SCHEMATIC),
            pcb_sync.EXPECTED_SCHEMATIC_HASH,
        )

    def test_sync_plan_normalizes_root_net_names_and_rejects_invalid_board_net_forms(self):
        import tools.sync_debug_connectors as pcb_sync

        slash_prefixed_changes = []
        for index, reference in enumerate(sorted(CONNECTOR_PAD_NETS), start=1):
            slash_prefixed_changes.append(
                {
                    **sync_change(reference, 300.0 + index, 90.0 + index),
                    "pad_nets": {
                        number: f"/{net_name}"
                        for number, net_name in CONNECTOR_PAD_NETS[reference].items()
                    },
                }
            )
        slash_prefixed_plan = sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
            changes=slash_prefixed_changes,
        )
        self.assertIs(
            pcb_sync._validate_sync_plan(
                slash_prefixed_plan,
                expected_status="ready",
                expected_board_only=23,
                expected_board_only_applied=0,
                expected_added_applied=0,
                expected_skipped_applied=0,
                require_undo=False,
            ),
            slash_prefixed_plan,
        )

        plain_plan = sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
        )
        self.assertIs(
            pcb_sync._validate_sync_plan(
                plain_plan,
                expected_status="ready",
                expected_board_only=23,
                expected_board_only_applied=0,
                expected_added_applied=0,
                expected_skipped_applied=0,
                require_undo=False,
            ),
            plain_plan,
        )

        wrong_pad_set = sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
            changes=[
                {**change, "pad_nets": {"1": "/VSYS"}}
                if change["reference"] == "J1"
                else change
                for change in default_sync_changes()
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "J1 pad_nets mismatch"):
            pcb_sync._validate_sync_plan(
                wrong_pad_set,
                expected_status="ready",
                expected_board_only=23,
                expected_board_only_applied=0,
                expected_added_applied=0,
                expected_skipped_applied=0,
                require_undo=False,
            )

        nested_root = sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
            changes=[
                {
                    **change,
                    "pad_nets": {
                        **CONNECTOR_PAD_NETS["J1"],
                        "1": "/sheet/VSYS",
                    },
                }
                if change["reference"] == "J1"
                else change
                for change in default_sync_changes()
            ],
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "J1 pad 1 board net has an unexpected hierarchical name: /sheet/VSYS",
        ):
            pcb_sync._validate_sync_plan(
                nested_root,
                expected_status="ready",
                expected_board_only=23,
                expected_board_only_applied=0,
                expected_added_applied=0,
                expected_skipped_applied=0,
                require_undo=False,
            )

        empty_net = sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
            changes=[
                {
                    **change,
                    "pad_nets": {
                        **CONNECTOR_PAD_NETS["J1"],
                        "1": "",
                    },
                }
                if change["reference"] == "J1"
                else change
                for change in default_sync_changes()
            ],
        )
        with self.assertRaisesRegex(
            RuntimeError, "J1 pad 1 board net must be a nonempty string"
        ):
            pcb_sync._validate_sync_plan(
                empty_net,
                expected_status="ready",
                expected_board_only=23,
                expected_board_only_applied=0,
                expected_added_applied=0,
                expected_skipped_applied=0,
                require_undo=False,
            )

        non_string_net = sync_plan_payload(
            status="ready",
            revision="rev-before",
            board_only_planned=23,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
            changes=[
                {
                    **change,
                    "pad_nets": {
                        **CONNECTOR_PAD_NETS["J1"],
                        "1": 123,
                    },
                }
                if change["reference"] == "J1"
                else change
                for change in default_sync_changes()
            ],
        )
        with self.assertRaisesRegex(
            RuntimeError, "J1 pad 1 board net must be a nonempty string"
        ):
            pcb_sync._validate_sync_plan(
                non_string_net,
                expected_status="ready",
                expected_board_only=23,
                expected_board_only_applied=0,
                expected_added_applied=0,
                expected_skipped_applied=0,
                require_undo=False,
            )

    def test_hash_gate_accepts_migrated_schematic_and_rejects_pre_migration_hash(self):
        import tools.sync_debug_connectors as pcb_sync

        migrated_schematic_hash = (
            "5322b7f21c10854aef14f7ca92ac35353f9fb9b7abd215451b4b4678a41aa1ac"
        )
        pre_migration_schematic_hash = (
            "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9"
        )

        self.assertEqual(pcb_sync.EXPECTED_SCHEMATIC_HASH, migrated_schematic_hash)

        with mock.patch(
            "tools.sync_debug_connectors._sha256",
            side_effect=[migrated_schematic_hash, pcb_sync.EXPECTED_BOARD_HASH],
        ):
            self.assertEqual(
                pcb_sync._validate_hashes(pcb_sync.SCHEMATIC, pcb_sync.BOARD),
                (migrated_schematic_hash, pcb_sync.EXPECTED_BOARD_HASH),
            )

        with mock.patch(
            "tools.sync_debug_connectors._sha256",
            side_effect=[pre_migration_schematic_hash, pcb_sync.EXPECTED_BOARD_HASH],
        ):
            with self.assertRaisesRegex(RuntimeError, "protected schematic hash mismatch"):
                pcb_sync._validate_hashes(pcb_sync.SCHEMATIC, pcb_sync.BOARD)

        with mock.patch(
            "tools.sync_debug_connectors._sha256",
            side_effect=[migrated_schematic_hash, "wrong-board-hash"],
        ):
            with self.assertRaisesRegex(RuntimeError, "protected PCB hash mismatch"):
                pcb_sync._validate_hashes(pcb_sync.SCHEMATIC, pcb_sync.BOARD)

    def test_literal_maps_and_exact_reference_inventories_are_frozen(self):
        from tools.sync_debug_connectors import (
            CONNECTOR_FOOTPRINTS as actual_footprints,
            CONNECTOR_PAD_NETS as actual_pad_nets,
            CONNECTOR_VALUES as actual_values,
            FINAL_BOARD_REFS,
            OLD_BOARD_REFS,
            REBIND_REFS as actual_rebind_refs,
            SHARED_REFS,
            TP_NETS as actual_tp_nets,
        )

        self.assertEqual(actual_tp_nets, TP_NETS)
        self.assertEqual(actual_pad_nets, CONNECTOR_PAD_NETS)
        self.assertEqual(actual_values, CONNECTOR_VALUES)
        self.assertEqual(actual_footprints, CONNECTOR_FOOTPRINTS)
        self.assertEqual(SHARED_REFS, shared_refs())
        self.assertEqual(actual_rebind_refs, REBIND_REFS)
        self.assertEqual(actual_rebind_refs, tuple(sorted(SHARED_REFS)))
        self.assertEqual(OLD_BOARD_REFS, old_board_refs())
        self.assertEqual(FINAL_BOARD_REFS, final_board_refs())
        self.assertEqual(len(SHARED_REFS), 146)
        self.assertEqual(len(actual_rebind_refs), 146)
        self.assertEqual(len(OLD_BOARD_REFS), 169)
        self.assertEqual(len(FINAL_BOARD_REFS), 152)
        self.assertFalse(any(reference.startswith("TP") for reference in SHARED_REFS))
        self.assertFalse(any(reference.startswith("J") for reference in OLD_BOARD_REFS))

    def test_capability_gate_requires_all_tools_and_every_invoked_input_property(self):
        from tools.sync_debug_connectors import require_pcb_sync_capabilities

        class GoodClient(FakeClient):
            pass

        require_pcb_sync_capabilities(GoodClient())

        cases = (
            ("pcb_components", "get_component_list", "board", "required"),
            ("pcb_components", "get_component_pads", "reference", "properties"),
            ("pcb_components", "delete_component", "tool", "tool"),
            ("pcb_board", "get_board_info", "board", "required"),
            ("pcb_routing", "query_traces", "net_name", "properties"),
            ("sch_export", "update_pcb_from_schematic", "expected_plan_revision", "properties"),
            ("sch_export", "rebind_pcb_schematic_identities", "tool", "tool"),
            ("sch_export", "rebind_pcb_schematic_identities", "references", "required"),
            ("sch_export", "rebind_pcb_schematic_identities", "dry_run", "properties"),
            ("sch_export", "rebind_pcb_schematic_identities", "expected_plan_revision", "properties"),
            ("manufacturing", "validate_for_manufacturing", "board", "properties"),
            ("verification", "run_drc", "severity", "properties"),
            ("project", "save_project", "tool", "tool"),
        )
        for toolset, tool, field, failure_mode in cases:
            schemas = complete_pcb_sync_schemas()
            if failure_mode == "tool":
                schemas[toolset].pop(tool)
            elif failure_mode == "required":
                schemas[toolset][tool]["required"].remove(field)
            else:
                schemas[toolset][tool]["properties"].pop(field)
            with self.subTest(tool=tool, field=field, failure_mode=failure_mode):
                with self.assertRaisesRegex(RuntimeError, tool):
                    require_pcb_sync_capabilities(FakeClient(schemas=schemas))

    def test_capability_gate_verifies_exact_toolset_ownership_on_real_client_surface(self):
        from tools.sync_debug_connectors import require_pcb_sync_capabilities

        require_pcb_sync_capabilities(ExactOwnershipClient())

        schemas = complete_pcb_sync_schemas()
        misplaced = schemas["pcb_routing"].pop("query_traces")
        schemas["pcb_components"]["query_traces"] = misplaced
        with self.assertRaisesRegex(RuntimeError, "pcb_routing.*query_traces"):
            require_pcb_sync_capabilities(ExactOwnershipClient(schemas))

        schemas = complete_pcb_sync_schemas()
        misplaced = schemas["sch_export"].pop("rebind_pcb_schematic_identities")
        schemas["pcb_components"]["rebind_pcb_schematic_identities"] = misplaced
        with self.assertRaisesRegex(
            RuntimeError, "sch_export.*rebind_pcb_schematic_identities"
        ):
            require_pcb_sync_capabilities(ExactOwnershipClient(schemas))

    def test_capability_gate_rejects_every_unexpected_required_input(self):
        from tools.sync_debug_connectors import require_pcb_sync_capabilities

        for toolset, tools in complete_pcb_sync_schemas().items():
            for tool in tools:
                with self.subTest(toolset=toolset, tool=tool):
                    schemas = complete_pcb_sync_schemas()
                    schemas[toolset][tool]["required"].append("unexpected_required")
                    schemas[toolset][tool]["properties"]["unexpected_required"] = {}
                    with self.assertRaisesRegex(RuntimeError, f"{tool}.*required"):
                        require_pcb_sync_capabilities(FakeClient(schemas=schemas))

    def test_query_traces_schema_accepts_board_as_only_required_input(self):
        from tools.sync_debug_connectors import require_pcb_sync_capabilities

        schemas = complete_pcb_sync_schemas()
        schemas["pcb_routing"]["query_traces"]["required"] = ["board"]
        require_pcb_sync_capabilities(FakeClient(schemas=schemas))

    def test_capture_baseline_collects_exact_live_state_and_never_saves_or_writes(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline

        client = FakeClient()
        queue_capture_baseline_flow(client)

        with mock.patch("tools.sync_debug_connectors._git_sha", return_value="d" * 40):
            baseline = capture_baseline(client, SCHEMATIC, BOARD)

        self.assertEqual(baseline["git_sha"], "d" * 40)
        self.assertEqual(baseline["schema_version"], 1)
        self.assertEqual(Path(baseline["schematic"]).resolve(), SCHEMATIC.resolve())
        self.assertEqual(Path(baseline["board"]).resolve(), BOARD.resolve())
        self.assertEqual(baseline["components"]["count"], 169)
        self.assertEqual(set(baseline["components"]["references"]), old_board_refs())
        self.assertEqual(len(baseline["components"]["items"]), 169)
        self.assertEqual(
            set(baseline["components"]["items"][0]),
            {"reference", "value", "footprint", "x", "y", "rotation", "layer"},
        )
        self.assertEqual(baseline["tp_nets"], TP_NETS)
        self.assertEqual(baseline["connector_pad_nets"], CONNECTOR_PAD_NETS)
        self.assertEqual(set(baseline["tp_pads"]), tp_refs())
        self.assertEqual(baseline["tp_pads"]["TP1"]["net"], "VSYS")
        self.assertEqual(baseline["tp_pads"]["TP1"]["board_net"], "/VSYS")
        self.assertEqual(set(baseline["traces"]), set(TP_NETS.values()))
        self.assertEqual(
            baseline["centroids"]["J1"],
            {
                "x": sum(10.0 + index for index in (1, 2, 3)) / 3.0,
                "y": sum(20.0 + index for index in (1, 2, 3)) / 3.0,
            },
        )
        self.assertEqual(baseline["board_info"]["zone_count"], 0)
        self.assertEqual(
            baseline["manufacturing"]["board_info"]["track_count"],
            0,
        )
        self.assertFalse(baseline["drc"]["truncated"])
        self.assertEqual(baseline["drc"]["categories_not_reported"], [])
        trace_calls = [
            arguments
            for name, arguments in client.calls
            if name == "query_traces"
        ]
        self.assertEqual(
            [arguments["net_name"] for arguments in trace_calls],
            [f"/{net_name}" for net_name in TP_NETS.values()],
        )
        forbidden = {
            "save_project",
            "delete_component",
            "move_component",
            "rotate_component",
            "flip_component",
            "route_trace",
            "route_pad_to_pad",
            "add_via",
            "update_pcb_from_schematic",
        }
        self.assertTrue(forbidden.isdisjoint({name for name, _ in client.calls}))

    def test_capture_baseline_refuses_inventory_or_track_or_trace_drift(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline

        missing_tp_client = FakeClient()
        missing_tp_client.queue_json(
            "get_component_list",
            component_list_payload(old_board_refs() - {"TP23"}),
        )
        with self.assertRaisesRegex(RuntimeError, "169"):
            capture_baseline(missing_tp_client, SCHEMATIC, BOARD)

        track_client = FakeClient()
        track_client.queue_json("get_component_list", component_list_payload(old_board_refs()))
        track_client.queue_json("get_board_info", board_info_payload())
        track_client.queue_json("validate_for_manufacturing", manufacturing_payload(track_count=1))
        with self.assertRaisesRegex(RuntimeError, "track_count"):
            capture_baseline(track_client, SCHEMATIC, BOARD)

        trace_client = FakeClient()
        trace_client.queue_json("get_component_list", component_list_payload(old_board_refs()))
        trace_client.queue_json("get_board_info", board_info_payload())
        trace_client.queue_json("validate_for_manufacturing", manufacturing_payload())
        for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
            trace_client.queue_json("get_component_pads", pad_payload(reference))
        trace_client.queue_json("get_component_list", component_list_payload(old_board_refs()))
        first_net = next(iter(TP_NETS.values()))
        trace_client.queue_json(
            "query_traces", {"count": 1, "traces": [{"net": f"/{first_net}"}]}
        )
        with self.assertRaisesRegex(RuntimeError, first_net):
            capture_baseline(trace_client, SCHEMATIC, BOARD)

    def test_capture_baseline_refuses_duplicate_or_miscounted_inventory_and_incomplete_drc(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline

        duplicate_client = FakeClient()
        duplicate_client.queue_json(
            "get_component_list",
            component_list_payload([*old_board_refs(), "TP1"]),
        )
        with self.assertRaisesRegex(RuntimeError, "duplicate.*TP1"):
            capture_baseline(duplicate_client, SCHEMATIC, BOARD)

        miscounted_client = FakeClient()
        miscounted = component_list_payload(old_board_refs())
        miscounted["count"] -= 1
        miscounted_client.queue_json("get_component_list", miscounted)
        with self.assertRaisesRegex(RuntimeError, "component count"):
            capture_baseline(miscounted_client, SCHEMATIC, BOARD)

        for incomplete_drc in (
            {},
            drc_payload(truncated=True),
            drc_payload(categories_not_reported=["schematic_parity"]),
        ):
            with self.subTest(incomplete_drc=incomplete_drc):
                client = FakeClient()
                queue_capture_baseline_flow(client, drc=incomplete_drc)
                with self.assertRaisesRegex(RuntimeError, "DRC.*complete"):
                    capture_baseline(client, SCHEMATIC, BOARD)

    def test_safety_count_fields_reject_booleans(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline, sync_debug_connectors

        component_client = FakeClient()
        components = component_list_payload(old_board_refs())
        components["count"] = False
        component_client.queue_json("get_component_list", components)
        with self.assertRaisesRegex(RuntimeError, "component count"):
            capture_baseline(component_client, SCHEMATIC, BOARD)

        cases = (
            ("zone_count", {"zone_count": False}),
            ("track_count", {"track_count": False}),
            (
                "VSYS",
                {
                    "trace_overrides": {
                        "/VSYS": {"count": False, "traces": []}
                    }
                },
            ),
        )
        for expected_error, overrides in cases:
            with self.subTest(expected_error=expected_error):
                client = FakeClient()
                queue_pre_delete_live_state(client, **overrides)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))

        coverage_client = FakeClient()
        queue_pre_delete_live_state(coverage_client)
        queue_rebind_stage(coverage_client)
        preview = sync_plan_payload(
            status="ready", revision="rev-before", board_only_planned=23,
            board_only_applied=0, skipped_applied=0, added_applied=0,
        )
        preview["coverage"]["footprints_updated"]["planned"] = False
        coverage_client.queue_json("update_pcb_from_schematic", preview)
        with self.assertRaisesRegex(RuntimeError, "footprints_updated"):
            sync_debug_connectors(coverage_client, SCHEMATIC, BOARD, baseline_fixture())

        drc_client = FakeClient()
        queue_capture_baseline_flow(
            drc_client, drc={**drc_payload(), "errors": False}
        )
        with self.assertRaisesRegex(RuntimeError, "DRC.*complete"):
            capture_baseline(drc_client, SCHEMATIC, BOARD)

    def test_empty_or_malformed_json_fails_closed_via_result_json(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline

        client = FakeClient()
        client.queue_raw("get_component_list", empty_result())
        with self.assertRaises(RuntimeError):
            capture_baseline(client, SCHEMATIC, BOARD)

        client = FakeClient()
        client.queue_raw("get_component_list", raw_text_result("not-json"))
        with self.assertRaises(RuntimeError):
            capture_baseline(client, SCHEMATIC, BOARD)

    def test_sync_refuses_any_pre_delete_mismatch_before_first_delete(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        bad_hash_baseline = {
            **baseline_fixture(),
            "schematic_hash": "wrong",
            "board_hash": "wrong",
        }
        client = FakeClient()
        with self.assertRaisesRegex(RuntimeError, "hash"):
            sync_debug_connectors(client, SCHEMATIC, BOARD, bad_hash_baseline)
        self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

        cases = (
            ("pre-delete 169", {"references": old_board_refs() - {"TP23"}}),
            ("zone_count", {"zone_count": 1}),
            ("track_count", {"track_count": 1}),
            (
                "COL0",
                {
                    "trace_overrides": {
                        "COL0": {"net_name": "COL0", "count": 1, "traces": [{"kind": "segment"}]}
                    }
                },
            ),
        )
        for expected_error, overrides in cases:
            with self.subTest(expected_error=expected_error):
                client = FakeClient()
                queue_pre_delete_live_state(client, **overrides)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_live_inventory_that_differs_from_the_captured_baseline(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        baseline = baseline_fixture()
        changed = component_list_payload(old_board_refs())
        changed["components"][0]["x"] += 0.5
        client = FakeClient()
        client.queue_json("get_component_list", changed)
        with self.assertRaisesRegex(RuntimeError, "live component inventory differs"):
            sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
        self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_live_tp_pad_state_that_differs_from_the_captured_baseline(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        baseline = baseline_fixture()
        baseline["tp_pads"]["TP1"]["x"] += 0.5
        baseline["centroids"]["J1"]["x"] += 0.5 / 3.0
        client = FakeClient()
        queue_pre_delete_live_state(client)
        with self.assertRaisesRegex(RuntimeError, "live TP pad state differs"):
            sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
        self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_rejects_incomplete_or_tampered_baseline_evidence_before_delete(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        mutations = (
            ("git_sha", lambda baseline: baseline.__setitem__("git_sha", "")),
            (
                "connector_values",
                lambda baseline: baseline["connector_values"].__setitem__("J1", "WRONG"),
            ),
            (
                "connector_footprints",
                lambda baseline: baseline["connector_footprints"].__setitem__("J1", "wrong:fp"),
            ),
            ("tp_pads", lambda baseline: baseline["tp_pads"].pop("TP23")),
            ("centroids", lambda baseline: baseline["centroids"]["J1"].__setitem__("x", 999.0)),
            ("board_info", lambda baseline: baseline["board_info"].__setitem__("zone_count", 1)),
            ("manufacturing", lambda baseline: baseline["manufacturing"]["board_info"].__setitem__("track_count", 1)),
            ("traces", lambda baseline: baseline["traces"]["VSYS"].__setitem__("count", 1)),
            ("drc", lambda baseline: baseline["drc"].__setitem__("truncated", True)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                baseline = baseline_fixture()
                mutate(baseline)
                client = FakeClient()
                with self.assertRaisesRegex(RuntimeError, label):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_baseline_git_revision_allows_only_current_or_exact_report_only_child(self):
        import tools.sync_debug_connectors as pcb_sync

        current = "c" * 40
        parent = "b" * 40
        with mock.patch.object(pcb_sync, "_git_sha", return_value=current):
            pcb_sync._require_baseline_git_revision(current)

        with mock.patch.object(
            pcb_sync, "_git_sha", return_value=current
        ), mock.patch.object(
            pcb_sync,
            "_git_parent_and_changed_paths",
            return_value=(parent, [pcb_sync.BASELINE_REPORT_RELATIVE]),
        ):
            pcb_sync._require_baseline_git_revision(parent)

        rejected = (
            ("a" * 40, (parent, [pcb_sync.BASELINE_REPORT_RELATIVE])),
            (parent, ("a" * 40, [pcb_sync.BASELINE_REPORT_RELATIVE])),
            (parent, (parent, [pcb_sync.BASELINE_REPORT_RELATIVE, "tools/changed.py"])),
        )
        for baseline_sha, relation in rejected:
            with self.subTest(baseline_sha=baseline_sha, relation=relation):
                with mock.patch.object(
                    pcb_sync, "_git_sha", return_value=current
                ), mock.patch.object(
                    pcb_sync, "_git_parent_and_changed_paths", return_value=relation
                ):
                    with self.assertRaisesRegex(RuntimeError, "git_sha"):
                        pcb_sync._require_baseline_git_revision(baseline_sha)

    def test_sync_executes_exact_delete_review_apply_and_save_contract(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline, sync_debug_connectors

        capture_client = FakeClient()
        queue_capture_baseline_flow(capture_client)

        baseline = capture_baseline(capture_client, SCHEMATIC, BOARD)
        pre_save_positions = staged_connector_positions()
        post_save_positions = {
            reference: (x + 42.0, y + 17.0)
            for reference, (x, y) in pre_save_positions.items()
        }

        client = FakeClient()
        queue_pre_delete_live_state(client)
        queue_rebind_triplet(client)
        queue_rebind_readback(client)
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-before",
                board_only_planned=23,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
            client.queue_json("delete_component", {"deleted": reference})
        client.queue_json("get_component_list", component_list_payload(shared_refs()))
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
            sync_plan_payload(
                status="applied",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=3,
                added_applied=6,
                undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
            ),
        )
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=pre_save_positions,
            ),
        )
        for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
            client.queue_json("get_component_pads", connector_pad_payload(reference))
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="noop",
                revision="rev-pre-save-noop",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=pre_save_positions,
            ),
        )
        for net_name in TP_NETS.values():
            client.queue_json("query_traces", empty_trace_payload(net_name))
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=pre_save_positions,
            ),
        )
        client.queue_raw("save_project", raw_text_result("Board saved successfully."))
        post_save_components = component_list_payload(
            final_board_refs(),
            connector_positions=post_save_positions,
        )
        client.queue_json("get_component_list", post_save_components)
        for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
            client.queue_json("get_component_pads", connector_pad_payload(reference))
        client.queue_json("get_board_info", board_info_payload())
        client.queue_json("validate_for_manufacturing", manufacturing_payload())
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=post_save_positions,
            ),
        )
        for net_name in TP_NETS.values():
            client.queue_json("query_traces", empty_trace_payload(net_name))
        client.queue_json("run_drc", drc_payload())
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="noop",
                revision="rev-noop",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )

        hash_events = []
        board_hash_calls = 0

        def fake_hash(path):
            nonlocal board_hash_calls
            hash_events.append(("hash", path.resolve()))
            if path.resolve() == SCHEMATIC.resolve():
                return pcb_sync.EXPECTED_SCHEMATIC_HASH
            board_hash_calls += 1
            if board_hash_calls == 1:
                return "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664"
            return "saved-board-hash"

        original_call_tool = client.call_tool

        def recording_call_tool(name, arguments):
            hash_events.append((name, deepcopy(arguments)))
            return original_call_tool(name, arguments)

        client.call_tool = recording_call_tool
        with mock.patch("tools.sync_debug_connectors._sha256", side_effect=fake_hash):
            evidence = sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)

        delete_calls = [
            (name, arguments)
            for name, arguments in client.calls
            if name == "delete_component"
        ]
        self.assertEqual(
            [arguments["reference"] for _, arguments in delete_calls],
            [f"TP{index}" for index in range(1, 24)],
        )
        update_calls = [
            (name, arguments)
            for name, arguments in client.calls
            if name == "update_pcb_from_schematic"
        ]
        rebind_calls = [
            (name, arguments)
            for name, arguments in client.calls
            if name == "rebind_pcb_schematic_identities"
        ]
        self.assertEqual(
            rebind_calls,
            [
                (
                    "rebind_pcb_schematic_identities",
                    {
                        "schematic": str(SCHEMATIC.resolve()),
                        "board": str(BOARD.resolve()),
                        "references": list(REBIND_REFS),
                        "dry_run": True,
                    },
                ),
                (
                    "rebind_pcb_schematic_identities",
                    {
                        "schematic": str(SCHEMATIC.resolve()),
                        "board": str(BOARD.resolve()),
                        "references": list(REBIND_REFS),
                        "dry_run": False,
                        "expected_plan_revision": "rebind-rev",
                    },
                ),
                (
                    "rebind_pcb_schematic_identities",
                    {
                        "schematic": str(SCHEMATIC.resolve()),
                        "board": str(BOARD.resolve()),
                        "references": list(REBIND_REFS),
                        "dry_run": True,
                    },
                ),
            ],
        )
        self.assertEqual(len(update_calls), 5)
        self.assertEqual(update_calls[0][1]["dry_run"], True)
        self.assertNotIn("expected_plan_revision", update_calls[0][1])
        self.assertEqual(update_calls[1][1]["dry_run"], True)
        self.assertEqual(
            update_calls[2][1],
            {
                "schematic": str(SCHEMATIC.resolve()),
                "board": str(BOARD.resolve()),
                "dry_run": False,
                "expected_plan_revision": "rev-after",
            },
        )
        self.assertEqual(
            update_calls[3][1],
            {
                "schematic": str(SCHEMATIC.resolve()),
                "board": str(BOARD.resolve()),
                "dry_run": True,
            },
        )
        self.assertEqual(
            update_calls[4][1],
            {
                "schematic": str(SCHEMATIC.resolve()),
                "board": str(BOARD.resolve()),
                "dry_run": True,
            },
        )
        save_index = next(
            index
            for index, (name, _) in enumerate(client.calls)
            if name == "save_project"
        )
        post_save_validation_indices = [
            max(
                index
                for index, (name, arguments) in enumerate(client.calls)
                if name == "get_component_pads"
                and arguments["reference"] in {f"J{index}" for index in range(1, 7)}
            ),
            max(index for index, (name, _) in enumerate(client.calls) if name == "get_board_info"),
            max(index for index, (name, _) in enumerate(client.calls) if name == "validate_for_manufacturing"),
            max(index for index, (name, _) in enumerate(client.calls) if name == "query_traces"),
            max(index for index, (name, _) in enumerate(client.calls) if name == "run_drc"),
            max(index for index, (name, _) in enumerate(client.calls) if name == "update_pcb_from_schematic"),
        ]
        self.assertLess(save_index, min(post_save_validation_indices))
        pre_save_noop_index = [
            index
            for index, (name, arguments) in enumerate(client.calls)
            if name == "update_pcb_from_schematic"
            and arguments == update_calls[3][1]
        ][0]
        self.assertLess(pre_save_noop_index, save_index)
        connector_pad_indices = [
            index
            for index, (name, arguments) in enumerate(client.calls)
            if name == "get_component_pads"
            and arguments["reference"] in {f"J{index}" for index in range(1, 7)}
        ]
        self.assertEqual(len(connector_pad_indices), 12)
        self.assertLess(max(connector_pad_indices[:6]), save_index)
        self.assertGreater(min(connector_pad_indices[6:]), save_index)
        self.assertEqual(
            sum(1 for name, _ in client.calls if name == "save_project"), 1
        )
        save_event_index = next(
            index for index, (name, _) in enumerate(hash_events) if name == "save_project"
        )
        after_hash_indices = [
            index for index, (name, _) in enumerate(hash_events) if name == "hash"
        ][-2:]
        self.assertGreater(min(after_hash_indices), save_event_index)
        self.assertEqual(evidence["apply"]["status"], "applied")
        self.assertEqual(evidence["rebind_dry_run"]["status"], "ready")
        self.assertEqual(evidence["rebind_apply"]["status"], "applied")
        self.assertEqual(evidence["rebind_noop"]["status"], "noop")
        self.assertEqual(
            evidence["before_hashes"],
            {
                "schematic": pcb_sync.EXPECTED_SCHEMATIC_HASH,
                "board": "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
            },
        )
        self.assertEqual(set(evidence["pre_save"]["connectors"]), {f"J{index}" for index in range(1, 7)})
        for reference, component in evidence["pre_save"]["connectors"].items():
            self.assertEqual(component["value"], CONNECTOR_VALUES[reference])
            self.assertEqual(component["footprint"], CONNECTOR_FOOTPRINTS[reference])
            self.assertEqual(component["layer"], "F.Cu")
            self.assertEqual(
                (component["x"], component["y"]),
                pre_save_positions[reference],
            )
        self.assertEqual(set(evidence["post_save"]["connector_pads"]), {f"J{index}" for index in range(1, 7)})
        self.assertEqual(set(evidence["post_save"]["connectors"]), {f"J{index}" for index in range(1, 7)})
        for reference, component in evidence["post_save"]["connectors"].items():
            self.assertEqual(component["value"], CONNECTOR_VALUES[reference])
            self.assertEqual(component["footprint"], CONNECTOR_FOOTPRINTS[reference])
            self.assertEqual(component["layer"], "F.Cu")
            self.assertEqual(
                (component["x"], component["y"]),
                post_save_positions[reference],
            )
            self.assertNotEqual(
                (component["x"], component["y"]),
                (
                    evidence["pre_save"]["connectors"][reference]["x"],
                    evidence["pre_save"]["connectors"][reference]["y"],
                ),
            )
        self.assertEqual(evidence["final_noop"]["status"], "noop")
        self.assertEqual(
            evidence["after_hashes"],
            {
                "schematic": pcb_sync.EXPECTED_SCHEMATIC_HASH,
                "board": "saved-board-hash",
            },
        )
        query_indices = [
            index for index, (name, _) in enumerate(client.calls) if name == "query_traces"
        ]
        self.assertEqual(len(query_indices), 92)
        self.assertEqual(client.calls[query_indices[0] - 1][0], "get_component_list")
        self.assertEqual(client.calls[query_indices[23] - 1][0], "get_component_list")
        self.assertEqual(client.calls[query_indices[46] - 1][0], "get_component_list")
        self.assertEqual(client.calls[query_indices[69] - 1][0], "get_component_list")
        forbidden = {
            "move_component",
            "rotate_component",
            "flip_component",
            "route_trace",
            "route_pad_to_pad",
            "add_via",
        }
        self.assertTrue(forbidden.isdisjoint({name for name, _ in client.calls}))

    def test_sync_rejects_bad_rebind_dry_run_before_delete_or_save(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        client = FakeClient()
        queue_pre_delete_live_state(client)
        queue_rebind_triplet(
            client,
            dry=rebind_plan_payload(
                status="applied",
                revision="rebind-rev",
                requested=146,
                eligible=146,
                planned=146,
                applied=146,
                conflicts=0,
                undo="unexpected undo",
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "rebind status mismatch: expected ready"):
            sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
        self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_rebind_validator_rejects_invalid_or_equal_symbol_paths(self):
        from tools.sync_debug_connectors import _validate_rebind_plan

        cases = (
            ("invalid old path", "old_symbol_path", "/not-a-uuid", "old_symbol_path"),
            ("invalid new path", "new_symbol_path", "//11111111-0000-4000-8000-000000000001", "new_symbol_path"),
            ("equal paths", "new_symbol_path", None, "symbol paths must differ"),
        )
        for label, field, value, expected_error in cases:
            with self.subTest(label=label):
                payload = rebind_plan_payload(
                    status="ready", revision="rebind-rev", requested=146, eligible=146,
                    planned=146, applied=0, conflicts=0,
                )
                if value is None:
                    payload["changes"][0][field] = payload["changes"][0]["old_symbol_path"]
                else:
                    payload["changes"][0][field] = value
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    _validate_rebind_plan(
                        payload, expected_status="ready", expected_planned=146,
                        expected_applied=0, require_undo=False,
                    )

    def test_rebind_validator_refuses_full_plan_contract_drift(self):
        from tools.sync_debug_connectors import _validate_rebind_plan

        def ready_payload():
            return rebind_plan_payload(
                status="ready", revision="rebind-rev", requested=146, eligible=146,
                planned=146, applied=0, conflicts=0,
            )

        cases = (
            ("top fields", lambda payload: payload.__setitem__("extra", True), "plan fields"),
            ("empty revision", lambda payload: payload.__setitem__("plan_revision", ""), "plan_revision"),
            ("diagnostics", lambda payload: payload.__setitem__("diagnostics", [{}]), "diagnostic"),
            ("coverage fields", lambda payload: payload["coverage"].pop("source"), "coverage fields"),
            ("bool count", lambda payload: payload["coverage"].__setitem__("requested", True), "coverage requested"),
            ("wrong count", lambda payload: payload["coverage"].__setitem__("eligible", 145), "coverage eligible"),
            ("unknown reference", lambda payload: payload["changes"][0].__setitem__("reference", "R999"), "change references"),
            ("permuted references", lambda payload: payload["changes"].reverse(), "change order"),
            ("extra change field", lambda payload: payload["changes"][0].__setitem__("extra", True), "change fields"),
            ("bad kiid", lambda payload: payload["changes"][0].__setitem__("kiid", "not-a-uuid"), "kiid"),
            ("value drift", lambda payload: payload["changes"][0].__setitem__("value", "WRONG"), "value mismatch"),
            ("footprint drift", lambda payload: payload["changes"][0].__setitem__("footprint_id", "wrong:fp"), "footprint_id mismatch"),
            ("dnp drift", lambda payload: payload["changes"][0].__setitem__("dnp", True), "dnp mismatch"),
            ("pad drift", lambda payload: payload["changes"][0].__setitem__("pad_nets", {}), "pad_nets mismatch"),
            ("preserve shape", lambda payload: payload["changes"][0]["preserve"].pop("locked"), "preserve shape"),
            ("preserve bool", lambda payload: payload["changes"][0]["preserve"].__setitem__("locked", 1), "preserve locked"),
            ("dry undo", lambda payload: payload.__setitem__("undo", "unexpected"), "dry-run/noop"),
        )
        for label, mutate, expected_error in cases:
            with self.subTest(label=label):
                payload = ready_payload()
                mutate(payload)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    _validate_rebind_plan(
                        payload, expected_status="ready", expected_planned=146,
                        expected_applied=0, require_undo=False,
                    )

        apply_payload = rebind_plan_payload(
            status="applied", revision="rebind-rev", requested=146, eligible=146,
            planned=146, applied=146, conflicts=0, undo="",
        )
        with self.assertRaisesRegex(RuntimeError, "undo guidance"):
            _validate_rebind_plan(
                apply_payload, expected_status="applied", expected_planned=146,
                expected_applied=146, require_undo=True,
            )

    def test_sync_refuses_rebind_transaction_failures_before_normal_sync_delete_or_save(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        cases = (
            (
                "apply revision mismatch",
                lambda client: queue_rebind_triplet(
                    client,
                    apply=rebind_plan_payload(
                        status="applied", revision="different-revision", requested=146,
                        eligible=146, planned=146, applied=146, conflicts=0, undo="undo",
                    ),
                ),
                "rebind apply result plan_revision differs",
            ),
            (
                "final non-noop",
                lambda client: queue_rebind_triplet(
                    client,
                    noop=rebind_plan_payload(
                        status="ready", revision="rebind-noop", requested=146,
                        eligible=146, planned=146, applied=0, conflicts=0,
                    ),
                ),
                "rebind status mismatch: expected noop",
            ),
        )
        for label, queue, expected_error in cases:
            with self.subTest(label=label):
                client = FakeClient()
                queue_pre_delete_live_state(client)
                queue(client)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "update_pcb_from_schematic" for name, _ in client.calls))
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_malformed_or_structured_rebind_errors_before_mutation(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        for response in (empty_result(), raw_text_result("not-json"), RuntimeError("invalid_argument")):
            with self.subTest(response=response):
                client = FakeClient()
                queue_pre_delete_live_state(client)
                client.queue_raw("rebind_pcb_schematic_identities", response)
                with self.assertRaises(RuntimeError):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "update_pcb_from_schematic" for name, _ in client.calls))
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_rebind_readback_evidence_drift_before_normal_sync_delete_or_save(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        pad_drift = pad_payload("TP1")
        pad_drift["pads"][0]["net"] = "/WRONG"
        cases = (
            ("inventory", {"references": old_board_refs() - {"TP23"}}, "post-rebind 169 references"),
            ("pad", {"pad_overrides": {"TP1": pad_drift}}, "TP1 net mismatch"),
            (
                "trace",
                {"trace_overrides": {"VSYS": {"count": 1, "traces": [{"net": "/VSYS"}]}}},
                "VSYS must have zero board traces",
            ),
        )
        for label, readback_kwargs, expected_error in cases:
            with self.subTest(label=label):
                client = FakeClient()
                queue_pre_delete_live_state(client)
                queue_rebind_triplet(client)
                queue_rebind_readback(client, **readback_kwargs)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "update_pcb_from_schematic" for name, _ in client.calls))
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_rejects_bad_first_dry_run_contract_before_delete_and_never_saves(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline, sync_debug_connectors

        capture_client = FakeClient()
        queue_capture_baseline_flow(capture_client)
        baseline = capture_baseline(capture_client, SCHEMATIC, BOARD)

        cases = (
            (
                "status mismatch: expected ready",
                sync_plan_payload(
                    status="applied",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    undo="not-allowed",
                ),
            ),
            (
                "diagnostic",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    diagnostics=[{"code": "board_readback_differs", "message": "drift"}],
                ),
            ),
            (
                "sync coverage metadata mismatch",
                {
                    **sync_plan_payload(
                        status="ready",
                        revision="rev-before",
                        board_only_planned=23,
                        board_only_applied=0,
                        skipped_applied=0,
                        added_applied=0,
                    ),
                    "coverage": {
                        **sync_plan_payload(
                            status="ready",
                            revision="rev-before",
                            board_only_planned=23,
                            board_only_applied=0,
                            skipped_applied=0,
                            added_applied=0,
                        )["coverage"],
                        "transport": "file_fallback",
                    },
                },
            ),
            (
                "board_only_preserved",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=22,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                ),
            ),
            (
                "sync must report exactly six add changes",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    changes=default_sync_changes()[:5],
                ),
            ),
            (
                "only add changes are allowed",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    changes=[{**change, "kind": "update"} if change["reference"] == "J1" else change for change in default_sync_changes()],
                ),
            ),
            (
                "J1 value mismatch",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    changes=[{**change, "value": "WRONG"} if change["reference"] == "J1" else change for change in default_sync_changes()],
                ),
            ),
            (
                "J1 footprint mismatch",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    changes=[
                        {**change, "footprint_id": "wrong:Footprint"}
                        if change["reference"] == "J1"
                        else change
                        for change in default_sync_changes()
                    ],
                ),
            ),
            (
                "J1 dnp must be false",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    changes=[{**change, "dnp": True} if change["reference"] == "J1" else change for change in default_sync_changes()],
                ),
            ),
            (
                "J1 pad_nets mismatch",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                    changes=[
                        {**change, "pad_nets": {"1": "WRONG"}}
                        if change["reference"] == "J1"
                        else change
                        for change in default_sync_changes()
                    ],
                ),
            ),
        )

        for expected_error, preview in cases:
            with self.subTest(expected_error=expected_error):
                client = FakeClient()
                queue_pre_delete_live_state(client)
                queue_rebind_stage(client)
                client.queue_json("update_pcb_from_schematic", preview)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_fails_closed_on_empty_or_malformed_json_before_delete(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        for response in (empty_result(), raw_text_result("not-json")):
            with self.subTest(response=response):
                client = FakeClient()
                queue_pre_delete_live_state(client)
                queue_rebind_stage(client)
                client.queue_raw("update_pcb_from_schematic", response)
                with self.assertRaises(RuntimeError):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "delete_component" for name, _ in client.calls))
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_if_remaining_tp_is_still_present_after_deletes(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline, sync_debug_connectors

        capture_client = FakeClient()
        queue_capture_baseline_flow(capture_client)
        baseline = capture_baseline(capture_client, SCHEMATIC, BOARD)

        client = FakeClient()
        queue_pre_delete_live_state(client)
        queue_rebind_stage(client)
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-before",
                board_only_planned=23,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
            client.queue_json("delete_component", {"deleted": reference})
        client.queue_json(
            "get_component_list",
            component_list_payload(shared_refs() | {"TP23"}),
        )

        with self.assertRaisesRegex(RuntimeError, "TP23"):
            sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)

        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_bad_delete_second_plan_apply_or_final_state_without_saving(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        second_dry_bad = sync_plan_payload(
            status="ready",
            revision="rev-after",
            board_only_planned=1,
            board_only_applied=0,
            skipped_applied=0,
            added_applied=0,
        )
        apply_bad = sync_plan_payload(
            status="applied",
            revision="rev-after",
            board_only_planned=0,
            board_only_applied=0,
            skipped_applied=3,
            added_applied=6,
            undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
            diagnostics=[{"code": "board_readback_differs", "message": "drift"}],
        )
        cases = (
            (
                "delete response mismatch for TP7",
                {"delete_overrides": {"TP7": {"deleted": "TP8"}}},
                None,
            ),
            ("board_only_preserved", {"second_dry": second_dry_bad}, None),
            (
                "second dry-run plan_revision must differ",
                {
                    "second_dry": sync_plan_payload(
                        status="ready",
                        revision="rev-before",
                        board_only_planned=0,
                        board_only_applied=0,
                        skipped_applied=0,
                        added_applied=0,
                    )
                },
                None,
            ),
            ("diagnostic", {"apply": apply_bad}, None),
            (
                "apply result plan_revision differs",
                {
                    "apply": sync_plan_payload(
                        status="applied",
                        revision="different-revision",
                        board_only_planned=0,
                        board_only_applied=0,
                        skipped_applied=3,
                        added_applied=6,
                        undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
                    )
                },
                None,
            ),
            ("final 152", {}, final_board_refs() - {"J6"}),
        )
        for expected_error, flow_kwargs, final_refs in cases:
            with self.subTest(expected_error=expected_error):
                client = FakeClient()
                queue_sync_through_apply(
                    client, **flow_kwargs, pre_save_references=final_refs
                )
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_post_save_validation_failure_never_saves_twice(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        cases = ("attribute", "pad", "zone", "track", "trace", "drc")
        for failure in cases:
            with self.subTest(failure=failure):
                client = FakeClient()
                queue_sync_through_apply(client)
                client.queue_raw(
                    "save_project", raw_text_result("Board saved successfully.")
                )
                post_save_components = component_list_payload(final_board_refs())
                if failure == "attribute":
                    next(
                        component
                        for component in post_save_components["components"]
                        if component["reference"] == "J1"
                    )["layer"] = "B.Cu"
                for component in post_save_components["components"]:
                    if component["reference"].startswith("J"):
                        component["x"] += 300.0
                client.queue_json("get_component_list", post_save_components)
                for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
                    payload = connector_pad_payload(reference)
                    if failure == "pad" and reference == "J1":
                        payload["pads"][0]["net"] = "WRONG"
                    client.queue_json("get_component_pads", payload)
                client.queue_json(
                    "get_board_info", board_info_payload(zone_count=1 if failure == "zone" else 0)
                )
                client.queue_json(
                    "validate_for_manufacturing",
                    manufacturing_payload(track_count=1 if failure == "track" else 0),
                )
                client.queue_json(
                    "get_component_list", component_list_payload(final_board_refs())
                )
                first_net = next(iter(TP_NETS.values()))
                for net_name in TP_NETS.values():
                    client.queue_json(
                        "query_traces",
                        {"count": 1, "traces": [{"net": net_name}]}
                        if failure == "trace" and net_name == first_net
                        else empty_trace_payload(net_name),
                    )
                client.queue_json(
                    "run_drc",
                    drc_payload(truncated=True) if failure == "drc" else drc_payload(),
                )
                expected = {
                    "attribute": "J1.*layer",
                    "pad": "pad-net mismatch",
                    "zone": "zone_count",
                    "track": "track_count",
                    "trace": first_net,
                    "drc": "DRC.*complete",
                }[failure]
                baseline = baseline_fixture()
                hash_values = iter(
                    (
                        pcb_sync.EXPECTED_SCHEMATIC_HASH,
                        "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
                        pcb_sync.EXPECTED_SCHEMATIC_HASH,
                        "saved-board-hash",
                    )
                )
                with mock.patch(
                    "tools.sync_debug_connectors._sha256", side_effect=lambda _path: next(hash_values)
                ):
                    with self.assertRaisesRegex(RuntimeError, expected):
                        sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
                self.assertEqual(
                    sum(1 for name, _ in client.calls if name == "save_project"), 1
                )

    def test_sync_rejects_pre_save_connector_staged_inside_board_before_save(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        pre_save_positions = staged_connector_positions()
        pre_save_positions["J1"] = (10.0, 10.0)
        baseline = baseline_fixture()

        client = FakeClient()
        queue_sync_through_apply(
            client,
            pre_save_connector_positions=pre_save_positions,
        )
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=pre_save_positions,
            ),
        )

        hash_values = iter(
            (
                pcb_sync.EXPECTED_SCHEMATIC_HASH,
                pcb_sync.EXPECTED_BOARD_HASH,
            )
        )
        with mock.patch(
            "tools.sync_debug_connectors._sha256", side_effect=lambda _path: next(hash_values)
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "J1 staged connector must remain outside board bounds",
            ):
                sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_rejects_pre_save_connector_gate_failures_before_save(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        baseline = baseline_fixture()
        cases = (
            (
                "layer",
                pre_save_gate_failure_inventory(layer_by_reference={"J1": "B.Cu"}),
                "J1 layer mismatch: expected F.Cu",
            ),
            (
                "non-finite x",
                pre_save_gate_failure_inventory(x_by_reference={"J1": float("nan")}),
                "J1 component x must be a finite number",
            ),
            (
                "non-finite y",
                pre_save_gate_failure_inventory(y_by_reference={"J1": float("inf")}),
                "J1 component y must be a finite number",
            ),
        )
        for label, final_inventory, expected_error in cases:
            with self.subTest(label=label):
                client = FakeClient()
                queue_pre_delete_live_state(client)
                queue_rebind_triplet(client)
                queue_rebind_readback(client)
                client.queue_json(
                    "update_pcb_from_schematic",
                    sync_plan_payload(
                        status="ready",
                        revision="rev-before",
                        board_only_planned=23,
                        board_only_applied=0,
                        skipped_applied=0,
                        added_applied=0,
                    ),
                )
                for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
                    client.queue_json("delete_component", {"deleted": reference})
                client.queue_json("get_component_list", component_list_payload(shared_refs()))
                client.queue_json(
                    "update_pcb_from_schematic",
                    sync_plan_payload(
                        status="ready",
                        revision="rev-after",
                        board_only_planned=0,
                        board_only_applied=0,
                        skipped_applied=0,
                        added_applied=0,
                    ),
                    sync_plan_payload(
                        status="applied",
                        revision="rev-after",
                        board_only_planned=0,
                        board_only_applied=0,
                        skipped_applied=3,
                        added_applied=6,
                        undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
                    ),
                )
                client.queue_json(
                    "get_component_list",
                    component_list_payload(
                        final_board_refs(),
                        connector_positions=staged_connector_positions(),
                    ),
                )
                for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
                    client.queue_json("get_component_pads", connector_pad_payload(reference))
                client.queue_json(
                    "get_component_list",
                    component_list_payload(
                        final_board_refs(),
                        connector_positions=staged_connector_positions(),
                    ),
                )
                client.queue_json(
                    "update_pcb_from_schematic",
                    sync_plan_payload(
                        status="noop",
                        revision="rev-pre-save-noop",
                        board_only_planned=0,
                        board_only_applied=0,
                        skipped_applied=0,
                        added_applied=0,
                    ),
                )
                for net_name in TP_NETS.values():
                    client.queue_json("query_traces", empty_trace_payload(net_name))
                client.queue_json("get_component_list", final_inventory)

                hash_values = iter(
                    (
                        pcb_sync.EXPECTED_SCHEMATIC_HASH,
                        pcb_sync.EXPECTED_BOARD_HASH,
                    )
                )
                with mock.patch(
                    "tools.sync_debug_connectors._sha256", side_effect=lambda _path: next(hash_values)
                ):
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_binds_pre_save_gate_to_final_inventory_snapshot(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        baseline = baseline_fixture()
        client = FakeClient()
        queue_pre_delete_live_state(client)
        queue_rebind_triplet(client)
        queue_rebind_readback(client)
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-before",
                board_only_planned=23,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
            client.queue_json("delete_component", {"deleted": reference})
        client.queue_json("get_component_list", component_list_payload(shared_refs()))
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
            sync_plan_payload(
                status="applied",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=3,
                added_applied=6,
                undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
            ),
        )
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=staged_connector_positions(),
            ),
        )
        for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
            client.queue_json("get_component_pads", connector_pad_payload(reference))
        client.queue_json(
            "get_component_list",
            component_list_payload(
                final_board_refs(),
                connector_positions=staged_connector_positions(),
            ),
        )
        client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="noop",
                revision="rev-pre-save-noop",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        for net_name in TP_NETS.values():
            client.queue_json("query_traces", empty_trace_payload(net_name))
        client.queue_json(
            "get_component_list",
            pre_save_gate_failure_inventory(layer_by_reference={"J1": "B.Cu"}),
        )

        hash_values = iter(
            (
                pcb_sync.EXPECTED_SCHEMATIC_HASH,
                pcb_sync.EXPECTED_BOARD_HASH,
            )
        )
        with mock.patch(
            "tools.sync_debug_connectors._sha256", side_effect=lambda _path: next(hash_values)
        ):
            with self.assertRaisesRegex(RuntimeError, "J1 layer mismatch: expected F.Cu"):
                sync_debug_connectors(client, SCHEMATIC, BOARD, baseline)
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_refuses_empty_apply_undo_and_final_noop_drift(self):
        import tools.sync_debug_connectors as pcb_sync
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        apply_undo_client = FakeClient()
        queue_pre_delete_live_state(apply_undo_client)
        queue_rebind_stage(apply_undo_client)
        apply_undo_client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-before",
                board_only_planned=23,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
            apply_undo_client.queue_json("delete_component", {"deleted": reference})
        apply_undo_client.queue_json("get_component_list", component_list_payload(shared_refs()))
        apply_undo_client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
            sync_plan_payload(
                status="applied",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=3,
                added_applied=6,
                undo="",
            ),
        )
        # Apply validation occurs before the shared pre-save gates.
        with self.assertRaisesRegex(RuntimeError, "undo guidance"):
            sync_debug_connectors(apply_undo_client, SCHEMATIC, BOARD, baseline_fixture())
        self.assertFalse(any(name == "save_project" for name, _ in apply_undo_client.calls))

        noop_client = FakeClient()
        queue_pre_delete_live_state(noop_client)
        queue_rebind_stage(noop_client)
        noop_client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-before",
                board_only_planned=23,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
        )
        for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
            noop_client.queue_json("delete_component", {"deleted": reference})
        noop_client.queue_json("get_component_list", component_list_payload(shared_refs()))
        noop_client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="ready",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
            ),
            sync_plan_payload(
                status="applied",
                revision="rev-after",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=3,
                added_applied=6,
                undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
            ),
        )
        queue_pre_save_gates(noop_client)
        noop_client.queue_raw("save_project", raw_text_result("Board saved successfully."))
        noop_post_save = component_list_payload(final_board_refs())
        for component in noop_post_save["components"]:
            if component["reference"].startswith("J"):
                component["x"] += 300.0
        noop_client.queue_json("get_component_list", noop_post_save)
        for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
            noop_client.queue_json("get_component_pads", connector_pad_payload(reference))
        noop_client.queue_json("get_board_info", board_info_payload())
        noop_client.queue_json("validate_for_manufacturing", manufacturing_payload())
        noop_client.queue_json("get_component_list", component_list_payload(final_board_refs()))
        for net_name in TP_NETS.values():
            noop_client.queue_json("query_traces", empty_trace_payload(net_name))
        noop_client.queue_json("run_drc", drc_payload())
        noop_client.queue_json(
            "update_pcb_from_schematic",
            sync_plan_payload(
                status="noop",
                revision="rev-noop",
                board_only_planned=0,
                board_only_applied=0,
                skipped_applied=0,
                added_applied=0,
                changes=[sync_change("J1", 1.0, 2.0)],
            ),
        )
        hash_values = iter(
            (
                pcb_sync.EXPECTED_SCHEMATIC_HASH,
                "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
                pcb_sync.EXPECTED_SCHEMATIC_HASH,
                "saved-board-hash",
            )
        )
        baseline = baseline_fixture()
        with mock.patch(
            "tools.sync_debug_connectors._sha256", side_effect=lambda _path: next(hash_values)
        ):
            with self.assertRaisesRegex(RuntimeError, "noop must not report changes"):
                sync_debug_connectors(noop_client, SCHEMATIC, BOARD, baseline)
        self.assertEqual(
            sum(1 for name, _ in noop_client.calls if name == "save_project"),
            1,
        )

    def test_sync_uses_function_paths_for_hashes_instead_of_globals(self):
        import tools.sync_debug_connectors as pcb_sync

        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            schematic = directory_path / "custom.kicad_sch"
            board = directory_path / "custom.kicad_pcb"
            schematic.write_text("custom schematic\n")
            board.write_text("custom board\n")

            baseline_components = component_list_payload(old_board_refs())
            tp_pads = {
                reference: {
                    "number": "1",
                    "net": TP_NETS[reference],
                    "board_net": pad_payload(reference)["pads"][0]["net"],
                    "x": pad_payload(reference)["pads"][0]["x"],
                    "y": pad_payload(reference)["pads"][0]["y"],
                }
                for reference in sorted(tp_refs(), key=lambda item: int(item[2:]))
            }
            baseline = {
                "schema_version": 1,
                "git_sha": pcb_sync._git_sha(),
                "schematic": str(schematic.resolve()),
                "board": str(board.resolve()),
                "schematic_hash": pcb_sync.EXPECTED_SCHEMATIC_HASH,
                "board_hash": pcb_sync.EXPECTED_BOARD_HASH,
                "components": {
                    "count": baseline_components["count"],
                    "references": sorted(old_board_refs()),
                    "items": sorted(
                        baseline_components["components"],
                        key=lambda component: component["reference"],
                    ),
                },
                "tp_nets": TP_NETS,
                "connector_pad_nets": CONNECTOR_PAD_NETS,
                "connector_values": CONNECTOR_VALUES,
                "connector_footprints": CONNECTOR_FOOTPRINTS,
                "tp_pads": tp_pads,
                "centroids": {
                    "J1": {"x": 12.0, "y": 22.0},
                    "J2": {"x": 16.0, "y": 26.0},
                    "J3": {"x": 21.0, "y": 31.0},
                    "J4": {"x": 25.5, "y": 35.5},
                    "J5": {"x": 29.0, "y": 39.0},
                    "J6": {"x": 32.0, "y": 42.0},
                },
                "board_info": board_info_payload(),
                "manufacturing": manufacturing_payload(),
                "traces": {
                    net_name: {
                        "board_net": f"/{net_name}",
                        **empty_trace_payload(f"/{net_name}"),
                    }
                    for net_name in TP_NETS.values()
                },
                "drc": drc_payload(),
            }

            client = FakeClient()
            queue_pre_delete_live_state(client)
            queue_rebind_stage(client)
            client.queue_json(
                "update_pcb_from_schematic",
                sync_plan_payload(
                    status="ready",
                    revision="rev-before",
                    board_only_planned=23,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                ),
            )
            for reference in sorted(tp_refs(), key=lambda item: int(item[2:])):
                client.queue_json("delete_component", {"deleted": reference})
            client.queue_json("get_component_list", component_list_payload(shared_refs()))
            client.queue_json(
                "update_pcb_from_schematic",
                sync_plan_payload(
                    status="ready",
                    revision="rev-after",
                    board_only_planned=0,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                ),
                sync_plan_payload(
                    status="applied",
                    revision="rev-after",
                    board_only_planned=0,
                    board_only_applied=0,
                    skipped_applied=3,
                    added_applied=6,
                    undo="Ctrl-Z reverses the whole schematic-to-PCB update.",
                ),
            )
            queue_pre_save_gates(client)
            client.queue_raw("save_project", raw_text_result("Board saved successfully."))
            post_save_components = component_list_payload(final_board_refs())
            for component in post_save_components["components"]:
                if component["reference"].startswith("J"):
                    component["x"] += 300.0
            client.queue_json("get_component_list", post_save_components)
            for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
                client.queue_json("get_component_pads", connector_pad_payload(reference))
            client.queue_json("get_board_info", board_info_payload())
            client.queue_json("validate_for_manufacturing", manufacturing_payload())
            client.queue_json("get_component_list", component_list_payload(final_board_refs()))
            for net_name in TP_NETS.values():
                client.queue_json("query_traces", empty_trace_payload(net_name))
            client.queue_json("run_drc", drc_payload())
            client.queue_json(
                "update_pcb_from_schematic",
                sync_plan_payload(
                    status="noop",
                    revision="rev-noop",
                    board_only_planned=0,
                    board_only_applied=0,
                    skipped_applied=0,
                    added_applied=0,
                ),
            )

            board_hash_calls = 0

            def fake_hash(path):
                nonlocal board_hash_calls
                if path.resolve() == schematic.resolve():
                    return pcb_sync.EXPECTED_SCHEMATIC_HASH
                if path.resolve() == board.resolve():
                    board_hash_calls += 1
                    return (
                        pcb_sync.EXPECTED_BOARD_HASH
                        if board_hash_calls == 1
                        else "custom-saved-board-hash"
                    )
                raise AssertionError(f"global protected path was hashed: {path}")

            with mock.patch.object(
                pcb_sync,
                "_sha256",
                side_effect=fake_hash,
            ):
                evidence = pcb_sync.sync_debug_connectors(client, schematic, board, baseline)

        self.assertEqual(
            evidence["after_hashes"],
            {
                "schematic": pcb_sync.EXPECTED_SCHEMATIC_HASH,
                "board": "custom-saved-board-hash",
            },
        )
        self.assertEqual(
            sum(1 for name, _ in client.calls if name == "save_project"), 1
        )
        self.assertEqual(client.calls[-1][0], "update_pcb_from_schematic")

    def test_cli_writes_report_only_after_success_in_both_modes(self):
        import tools.sync_debug_connectors as pcb_sync

        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            report_path = directory_path / "nested" / "capture.json"

            fake_client = object()
            fake_context = mock.MagicMock()
            fake_context.__enter__.return_value = fake_client
            fake_context.__exit__.return_value = None

            with mock.patch.object(
                pcb_sync,
                "McpClient",
                return_value=fake_context,
            ), mock.patch.object(
                pcb_sync,
                "capture_baseline",
                return_value={"mode": "capture"},
            ):
                pcb_sync.main(
                    [
                        "--capture-baseline",
                        "--report",
                        str(report_path),
                    ]
                )
            self.assertEqual(json.loads(report_path.read_text()), {"mode": "capture"})
            self.assertEqual(list(report_path.parent.glob(".*.tmp")), [])

            report_path.unlink()
            baseline_path = directory_path / "baseline.json"
            baseline_path.write_text(json.dumps({"baseline": True}))
            with mock.patch.object(
                pcb_sync,
                "McpClient",
                return_value=fake_context,
            ), mock.patch.object(
                pcb_sync,
                "sync_debug_connectors",
                return_value={"mode": "apply"},
            ):
                pcb_sync.main(
                    [
                        "--apply",
                        "--baseline",
                        str(baseline_path),
                        "--report",
                        str(report_path),
                    ]
                )
            self.assertEqual(json.loads(report_path.read_text()), {"mode": "apply"})

            report_path.unlink()
            with mock.patch.object(
                pcb_sync,
                "McpClient",
                return_value=fake_context,
            ), mock.patch.object(
                pcb_sync,
                "capture_baseline",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    pcb_sync.main(
                        [
                            "--capture-baseline",
                            "--report",
                            str(report_path),
                        ]
                    )
            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
