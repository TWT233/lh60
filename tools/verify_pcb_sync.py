import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tools.lh60_design.mcp import McpClient


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
        },
        "pcb_board": {
            "get_board_info": schema(("board",), "board"),
        },
        "pcb_routing": {
            "query_traces": schema(("board",), "board", "net_name", "layer"),
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
        "manufacturing": {
            "validate_for_manufacturing": schema(("board",), "board"),
        },
        "verification": {
            "run_drc": schema(("board",), "board", "limit", "severity"),
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


def shared_refs():
    refs = {"U1"}
    refs.update({f"D{index}" for index in range(1, 71)})
    refs.update({f"SW{index}" for index in range(1, 59)})
    refs.update({f"SW{index}" for index in range(60, 77)})
    return refs


def tp_refs():
    return {f"TP{index}" for index in range(1, 24)}


def old_board_refs():
    return shared_refs() | tp_refs()


def final_board_refs():
    return shared_refs() | {f"J{index}" for index in range(1, 7)}


def component_list_payload(references):
    components = [
            {
                "reference": reference,
                "value": CONNECTOR_VALUES.get(reference, f"value-{reference}"),
                "footprint": CONNECTOR_FOOTPRINTS.get(
                    reference, f"library:{reference}"
                ),
                "layer": "F.Cu",
                "x": float(index),
                "y": float(index) / 2.0,
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


def queue_sync_through_apply(client, *, delete_overrides=None, second_dry=None, apply=None):
    queue_pre_delete_live_state(client)
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


class PcbSyncContractTest(unittest.TestCase):
    def test_literal_maps_and_exact_reference_inventories_are_frozen(self):
        from tools.sync_debug_connectors import (
            CONNECTOR_FOOTPRINTS as actual_footprints,
            CONNECTOR_PAD_NETS as actual_pad_nets,
            CONNECTOR_VALUES as actual_values,
            FINAL_BOARD_REFS,
            OLD_BOARD_REFS,
            SHARED_REFS,
            TP_NETS as actual_tp_nets,
        )

        self.assertEqual(actual_tp_nets, TP_NETS)
        self.assertEqual(actual_pad_nets, CONNECTOR_PAD_NETS)
        self.assertEqual(actual_values, CONNECTOR_VALUES)
        self.assertEqual(actual_footprints, CONNECTOR_FOOTPRINTS)
        self.assertEqual(SHARED_REFS, shared_refs())
        self.assertEqual(OLD_BOARD_REFS, old_board_refs())
        self.assertEqual(FINAL_BOARD_REFS, final_board_refs())
        self.assertEqual(len(SHARED_REFS), 146)
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
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, capture_baseline, sync_debug_connectors

        capture_client = FakeClient()
        queue_capture_baseline_flow(capture_client)

        baseline = capture_baseline(capture_client, SCHEMATIC, BOARD)

        client = FakeClient()
        queue_pre_delete_live_state(client)
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
        client.queue_json("get_component_list", component_list_payload(final_board_refs()))
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

        hash_events = []
        board_hash_calls = 0

        def fake_hash(path):
            nonlocal board_hash_calls
            hash_events.append(("hash", path.resolve()))
            if path.resolve() == SCHEMATIC.resolve():
                return "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9"
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
        self.assertEqual(len(update_calls), 4)
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
        self.assertEqual(
            evidence["before_hashes"],
            {
                "schematic": "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
                "board": "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
            },
        )
        self.assertEqual(set(evidence["post_save"]["connector_pads"]), {f"J{index}" for index in range(1, 7)})
        self.assertEqual(set(evidence["post_save"]["connectors"]), {f"J{index}" for index in range(1, 7)})
        for reference, component in evidence["post_save"]["connectors"].items():
            self.assertEqual(component["value"], CONNECTOR_VALUES[reference])
            self.assertEqual(component["footprint"], CONNECTOR_FOOTPRINTS[reference])
            self.assertEqual(component["layer"], "F.Cu")
        self.assertEqual(evidence["final_noop"]["status"], "noop")
        self.assertEqual(
            evidence["after_hashes"],
            {
                "schematic": "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
                "board": "saved-board-hash",
            },
        )
        query_indices = [
            index for index, (name, _) in enumerate(client.calls) if name == "query_traces"
        ]
        self.assertEqual(len(query_indices), 46)
        self.assertEqual(client.calls[query_indices[0] - 1][0], "get_component_list")
        self.assertEqual(client.calls[query_indices[23] - 1][0], "get_component_list")
        forbidden = {
            "move_component",
            "rotate_component",
            "flip_component",
            "route_trace",
            "route_pad_to_pad",
            "add_via",
        }
        self.assertTrue(forbidden.isdisjoint({name for name, _ in client.calls}))

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
                queue_sync_through_apply(client, **flow_kwargs)
                if final_refs is not None:
                    client.queue_json(
                        "get_component_list", component_list_payload(final_refs)
                    )
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    sync_debug_connectors(client, SCHEMATIC, BOARD, baseline_fixture())
                self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_sync_post_save_validation_failure_never_saves_twice(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        cases = ("attribute", "pad", "zone", "track", "trace", "drc")
        for failure in cases:
            with self.subTest(failure=failure):
                client = FakeClient()
                queue_sync_through_apply(client)
                client.queue_json(
                    "get_component_list", component_list_payload(final_board_refs())
                )
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
                        "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
                        "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
                        "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
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

    def test_sync_refuses_empty_apply_undo_and_final_noop_drift(self):
        from tools.sync_debug_connectors import BOARD, SCHEMATIC, sync_debug_connectors

        apply_undo_client = FakeClient()
        queue_pre_delete_live_state(apply_undo_client)
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
        with self.assertRaisesRegex(RuntimeError, "undo guidance"):
            sync_debug_connectors(apply_undo_client, SCHEMATIC, BOARD, baseline_fixture())
        self.assertFalse(any(name == "save_project" for name, _ in apply_undo_client.calls))

        noop_client = FakeClient()
        queue_pre_delete_live_state(noop_client)
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
        noop_client.queue_json("get_component_list", component_list_payload(final_board_refs()))
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
                "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
                "0a5722685ee378e9c9b240aa01a1f151f382cab83216edfa14a0663a1ac80664",
                "7ae8a38afc453579f8f24de23e57772eff73056d12acd4fd9fcc6f0bf57533f9",
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
            client.queue_json("get_component_list", component_list_payload(final_board_refs()))
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
