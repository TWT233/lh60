import json
from collections import defaultdict
from copy import deepcopy
import hashlib
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


def text_result(payload):
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def raw_text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def complete_pcb_acceptance_schemas():
    return {
        "pcb_components": {
            "get_component_list": schema(("board",), "board"),
            "get_component_pads": schema(("board", "reference"), "board", "reference"),
            "list_board_footprint_graphics": schema(("board", "reference", "layer"), "board", "reference", "layer"),
        },
        "verification": {
            "run_drc": schema(("board",), "board", "limit", "severity"),
        },
        "pcb_export": {
            "export_position_file": schema(("board", "output"), "board", "output", "format", "units", "side"),
        },
    }


def connector_component_inventory(*, connectors_on_back=True, pose_override=None, refs=None):
    from tools.lh60_design.pcb import frozen_connector_placements
    from tools.verify_pcb_sync import CONNECTOR_FOOTPRINTS, CONNECTOR_VALUES, final_board_refs

    refs = final_board_refs() if refs is None else refs
    pose_override = {} if pose_override is None else pose_override
    connector_by_ref = {placement.reference: placement for placement in frozen_connector_placements()}
    components = []
    for index, reference in enumerate(sorted(refs), start=1):
        if reference in connector_by_ref:
            placement = connector_by_ref[reference]
            x, y, rotation, layer = pose_override.get(
                reference,
                (
                    placement.x_mm,
                    placement.y_mm,
                    placement.rotation_deg,
                    "B.Cu" if connectors_on_back else "F.Cu",
                ),
            )
            components.append(
                {
                    "reference": reference,
                    "value": CONNECTOR_VALUES[reference],
                    "footprint": CONNECTOR_FOOTPRINTS[reference],
                    "layer": layer,
                    "x": x,
                    "y": y,
                    "rotation": rotation,
                }
            )
        else:
            components.append(
                {
                    "reference": reference,
                    "value": f"value-{reference}",
                    "footprint": f"library:{reference}",
                    "layer": "F.Cu",
                    "x": float(index),
                    "y": float(index) / 2.0,
                    "rotation": 0.0,
                }
            )
    return {"count": len(components), "components": components}


def connector_pad_payload(reference, *, net_override=None):
    from tools.verify_pcb_sync import CONNECTOR_PAD_NETS

    expected = CONNECTOR_PAD_NETS[reference]
    pads = []
    for number, net_name in expected.items():
        actual = net_override.get(number, net_name) if net_override else net_name
        pads.append(
            {
                "number": number,
                "net": f"/{actual}",
                "x": 100.0 + int(number),
                "y": 200.0 + int(number),
            }
        )
    return {"reference": reference, "pad_count": len(pads), "pads": pads}


def graphics_payload(layer, count):
    return {
        "count": count,
        "graphics": [
            {"layer": layer, "type": "line", "item_id": index}
            for index in range(count)
        ],
    }


def drc_payload(
    *,
    j_test_id="unconnected_items",
    total=530,
    unconnected=367,
    design=163,
    errors=367,
    warnings=163,
):
    return {
        "total_violations": total,
        "design_rule_violations": design,
        "unconnected_items": unconnected,
        "schematic_parity": 0,
        "filtered_count": 0,
        "errors": errors,
        "warnings": warnings,
        "severity_filter": "info",
        "shown": total,
        "truncated": False,
        "violations": [
            {
                "test_id": j_test_id,
                "severity": "warning",
                "layer": "B.Cu",
                "message": "connector finding",
                "references": ["J1"],
            }
        ],
    }


class FakeClient:
    result_json = staticmethod(McpClient.result_json)
    call_tool_json = McpClient.call_tool_json

    def __init__(self, schemas=None, position_csv="Ref,Val\nU1,MCU\n", export_should_write=True):
        self.schemas = deepcopy(schemas or complete_pcb_acceptance_schemas())
        self.loaded = {}
        self.responses = defaultdict(list)
        self.calls = []
        self.position_csv = position_csv
        self.export_should_write = export_should_write

    def request(self, method, arguments):
        self.calls.append((method, deepcopy(arguments)))
        if method != "tools/list" or arguments != {}:
            raise AssertionError((method, arguments))
        return {
            "tools": [
                {"name": name, "inputSchema": schema}
                for name, schema in self.loaded.items()
            ]
        }

    def queue_json(self, name, *payloads):
        for payload in payloads:
            self.responses[name].append(text_result(payload))

    def call_tool(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if name == "load_toolset":
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
        if name == "export_position_file":
            if self.export_should_write:
                Path(arguments["output"]).write_text(self.position_csv)
            return raw_text_result("positions exported")
        if not self.responses[name]:
            raise AssertionError(f"missing queued response for {name}")
        return deepcopy(self.responses[name].pop(0))


def queue_happy_path(client):
    client.queue_json("get_component_list", connector_component_inventory())
    for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
        for layer, count in (
            ("B.Fab", 1),
            ("B.CrtYd", 1),
            ("B.SilkS", 6),
            ("F.Fab", 0),
            ("F.CrtYd", 0),
            ("F.SilkS", 0),
        ):
            client.queue_json("list_board_footprint_graphics", graphics_payload(layer, count))
    for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
        client.queue_json("get_component_pads", connector_pad_payload(reference))
    client.queue_json("run_drc", drc_payload())


class PcbAcceptanceContractTest(unittest.TestCase):
    def test_capability_gate_requires_run_drc_and_export_position_contracts(self):
        from tools.check_pcb_acceptance import require_pcb_acceptance_capabilities

        schemas = complete_pcb_acceptance_schemas()
        schemas["verification"] = {}
        schemas["pcb_export"] = {
            "export_position_file": schema(("board", "output"), "board", "output", "format", "units", "side")
        }
        with self.assertRaisesRegex(RuntimeError, "run_drc"):
            require_pcb_acceptance_capabilities(FakeClient(schemas=schemas))

        schemas = complete_pcb_acceptance_schemas()
        schemas["pcb_export"] = {}
        with self.assertRaisesRegex(RuntimeError, "export_position_file"):
            require_pcb_acceptance_capabilities(FakeClient(schemas=schemas))

    def test_acceptance_happy_path_returns_hashes_coverage_and_never_saves(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        queue_happy_path(client)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")

            def fake_run(command, check, capture_output, text):
                self.assertEqual(
                    command,
                    [
                        "kicad-cli",
                        "pcb",
                        "export",
                        "svg",
                        "--output",
                        str(root / "back.svg"),
                        "--layers",
                        "B.SilkS,B.Fab,B.CrtYd,Edge.Cuts",
                        "--mode-single",
                        "--mirror",
                        "--exclude-drawing-sheet",
                        "--fit-page-to-board",
                        "--page-size-mode",
                        "2",
                        str(board.resolve()),
                    ],
                )
                (root / "back.svg").write_text("<svg/>")
                return mock.Mock(stdout="", stderr="", returncode=0)

            with mock.patch.object(checker, "_git_sha", return_value="a" * 40), mock.patch.object(
                checker.subprocess,
                "run",
                side_effect=fake_run,
            ):
                evidence = checker.acceptance_record(
                    client,
                    board,
                    output_dir=root,
                    kicad_cli=Path("kicad-cli"),
                )

        self.assertEqual(evidence["coverage"]["expected_refs"], 152)
        self.assertEqual(evidence["coverage"]["connector_pad_nets"], 23)
        self.assertEqual(evidence["connectors"]["J1"]["graphics"]["B.SilkS"], 6)
        self.assertEqual(evidence["pad_nets"]["J6"]["3"], "GP29")
        self.assertEqual(evidence["drc"]["total_violations"], 530)
        self.assertEqual(evidence["drc"]["design_rule_violations"], 163)
        self.assertEqual(evidence["drc"]["errors"], 367)
        self.assertEqual(evidence["drc"]["warnings"], 163)
        self.assertEqual(evidence["git_sha"], "a" * 40)
        self.assertEqual(
            evidence["board_sha256"],
            hashlib.sha256(b"board").hexdigest(),
        )
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_default_kicad_cli_prefers_local_binary(self):
        import tools.check_pcb_acceptance as checker

        expected = Path("/tmp/fake-kicad-cli")
        original_exists = Path.exists

        def fake_exists(path):
            if path == expected:
                return True
            return original_exists(path)

        with mock.patch.object(checker, "DEFAULT_KICAD_CLI", expected), mock.patch.object(
            Path,
            "exists",
            autospec=True,
            side_effect=fake_exists,
        ):
            self.assertEqual(
                checker.resolve_kicad_cli(),
                expected,
            )

    def test_acceptance_rejects_pose_drift(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json(
            "get_component_list",
            connector_component_inventory(pose_override={"J1": (999.0, 36.0, 0.0, "B.Cu")}),
        )

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "J1 x mismatch"):
                checker._require_connector_pose_and_graphics(client, board)

    def test_acceptance_rejects_layer_drift(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json(
            "get_component_list",
            connector_component_inventory(pose_override={"J1": (282.5, 36.0, 0.0, "F.Cu")}),
        )

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "J1 layer mismatch"):
                checker._require_connector_pose_and_graphics(client, board)

    def test_acceptance_rejects_graphics_drift(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("get_component_list", connector_component_inventory())
        for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
            layers = (
                ("B.Fab", 0 if reference == "J1" else 1),
                ("B.CrtYd", 1),
                ("B.SilkS", 6),
                ("F.Fab", 0),
                ("F.CrtYd", 0),
                ("F.SilkS", 0),
            )
            for layer, count in layers:
                client.queue_json("list_board_footprint_graphics", graphics_payload(layer, count))

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "J1 B.Fab graphic count mismatch"):
                checker._require_connector_pose_and_graphics(client, board)

    def test_acceptance_rejects_pad_net_drift(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        for reference in ("J1", "J2", "J3", "J4", "J5", "J6"):
            override = {"1": "WRONG"} if reference == "J1" else None
            client.queue_json("get_component_pads", connector_pad_payload(reference, net_override=override))

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "J1 pad-net mismatch"):
                checker._require_connector_pad_nets(client, board)

    def test_acceptance_rejects_unexpected_j_related_drc_findings(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("run_drc", drc_payload(j_test_id="clearance"))

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "unexpected J-related DRC finding"):
                checker._require_drc(client, board)

    def test_acceptance_rejects_drc_counter_drift(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("run_drc", drc_payload(total=531))

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "DRC total_violations mismatch"):
                checker._require_drc(client, board)

    def test_acceptance_rejects_position_export_with_connectors(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient(position_csv="Ref,Val\nJ1,PWR\n")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "position export must exclude J1"):
                checker._require_position_export_without_connectors(client, board, root / "positions.csv")

    def test_acceptance_rejects_missing_svg_output(self):
        import tools.check_pcb_acceptance as checker

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            with mock.patch.object(checker.subprocess, "run", return_value=mock.Mock(returncode=0)):
                with self.assertRaisesRegex(RuntimeError, "back SVG export missing"):
                    checker._export_back_svg(board, root / "back.svg", kicad_cli=Path("kicad-cli"))


if __name__ == "__main__":
    unittest.main()
