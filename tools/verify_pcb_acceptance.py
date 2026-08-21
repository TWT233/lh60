import json
from collections import defaultdict
from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from tools.lh60_design.mcp import McpClient


EXPECTED_CONNECTOR_ENDPOINTS = (
    ("J1", "1", "VSYS"),
    ("J1", "2", "3V3"),
    ("J1", "3", "GND"),
    ("J2", "1", "COL0"),
    ("J2", "2", "COL1"),
    ("J2", "3", "COL2"),
    ("J2", "4", "COL3"),
    ("J2", "5", "COL4"),
    ("J3", "1", "COL5"),
    ("J3", "2", "COL6"),
    ("J3", "3", "COL7"),
    ("J3", "4", "COL8"),
    ("J3", "5", "COL9"),
    ("J4", "1", "ROW0"),
    ("J4", "2", "ROW1"),
    ("J4", "3", "ROW2"),
    ("J4", "4", "ROW3"),
    ("J5", "1", "ROW4"),
    ("J5", "2", "ROW5"),
    ("J5", "3", "ROW6"),
    ("J6", "1", "GP27"),
    ("J6", "2", "GP28"),
    ("J6", "3", "GP29"),
)


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
            "list_board_footprint_graphics": schema(("board", "reference"), "board", "reference", "layer"),
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
    total=530,
    unconnected=367,
    design=163,
    errors=457,
    warnings=73,
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
                "rule": "unconnected_items",
                "description": "Unconnected between U1 and U2",
                "pos": {"x": 1.0, "y": 2.0},
                "severity": "warning",
            }
        ],
    }


def drc_report_text(*sections):
    lines = []
    for rule, entries in sections:
        lines.append(f"[{rule}]:")
        lines.extend(entries)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def connector_drc_report(
    endpoints=EXPECTED_CONNECTOR_ENDPOINTS,
    *,
    unrelated_unconnected=(),
    other_sections=(),
):
    lines = []
    for index, (reference, pad_number, net) in enumerate(endpoints, start=1):
        lines.extend(
            (
                "[unconnected_items]: Missing connection between items",
                "    Local override; error",
                f"    @({index:.4f} mm, {index + 1:.4f} mm): "
                f"PTH pad {pad_number} [/{net}] of {reference}",
                f"    @({index + 2:.4f} mm, {index + 3:.4f} mm): "
                f"Pad 1 [/{net}] of U{index} on F.Cu",
            )
        )
    for line in unrelated_unconnected:
        lines.extend(
            (
                "[unconnected_items]: Missing connection between items",
                "    Local override; error",
                line,
            )
        )
    for rule, entries in other_sections:
        lines.append(f"[{rule}]: Synthetic finding")
        lines.extend(entries)
    return "\n".join(lines).strip() + "\n"


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
    def require_drc_report(self, report_text, *, payload=None):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("run_drc", payload or drc_payload())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")

            def fake_run(command, check, capture_output, text):
                self.assertEqual(command[1:3], ["pcb", "drc"])
                (root / "drc.rpt").write_text(report_text)
                return mock.Mock(stdout="", stderr="", returncode=0)

            with mock.patch.object(checker.subprocess, "run", side_effect=fake_run):
                return checker._require_drc(
                    client,
                    board,
                    root,
                    kicad_cli=Path("kicad-cli"),
                )

    def test_capability_gate_accepts_real_list_board_footprint_graphics_schema(self):
        from tools.check_pcb_acceptance import require_pcb_acceptance_capabilities

        require_pcb_acceptance_capabilities(FakeClient())

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

    def test_capability_gate_rejects_list_board_footprint_graphics_required_drift(self):
        from tools.check_pcb_acceptance import require_pcb_acceptance_capabilities

        schemas = complete_pcb_acceptance_schemas()
        schemas["pcb_components"]["list_board_footprint_graphics"] = schema(
            ("board",),
            "board",
            "reference",
            "layer",
        )

        with self.assertRaisesRegex(RuntimeError, "list_board_footprint_graphics required inputs differ"):
            require_pcb_acceptance_capabilities(FakeClient(schemas=schemas))

    def test_capability_gate_rejects_list_board_footprint_graphics_missing_layer_property(self):
        from tools.check_pcb_acceptance import require_pcb_acceptance_capabilities

        schemas = complete_pcb_acceptance_schemas()
        schemas["pcb_components"]["list_board_footprint_graphics"] = schema(
            ("board", "reference"),
            "board",
            "reference",
        )

        with self.assertRaisesRegex(RuntimeError, "list_board_footprint_graphics missing \\['layer'\\]"):
            require_pcb_acceptance_capabilities(FakeClient(schemas=schemas))

    def test_acceptance_happy_path_returns_hashes_coverage_and_never_saves(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        queue_happy_path(client)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            drc_report = connector_drc_report(
                unrelated_unconnected=(
                    "    @(90.0000 mm, 91.0000 mm): PTH pad 2 [/ROW0] of SW1",
                ),
                other_sections=(("clearance", ["warning: Item of U1 to U2"]),),
            )

            def fake_run(command, check, capture_output, text):
                if command[1:3] == ["pcb", "drc"]:
                    self.assertEqual(
                        command,
                        [
                            "kicad-cli",
                            "pcb",
                            "drc",
                            "--format",
                            "report",
                            "--units",
                            "mm",
                            "--severity-all",
                            "--output",
                            str(root / "drc.rpt"),
                            str(board.resolve()),
                        ],
                    )
                    (root / "drc.rpt").write_text(drc_report)
                else:
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
        self.assertEqual(evidence["drc"]["errors"], 457)
        self.assertEqual(evidence["drc"]["warnings"], 73)
        self.assertEqual(
            evidence["drc"]["connector_unconnected_endpoints"],
            [
                {"reference": reference, "pad_number": pad_number, "net": net}
                for reference, pad_number, net in EXPECTED_CONNECTOR_ENDPOINTS
            ],
        )
        self.assertEqual(
            evidence["drc"]["report_sha256"],
            hashlib.sha256(drc_report.encode()).hexdigest(),
        )
        self.assertEqual(evidence["git_sha"], "a" * 40)
        self.assertEqual(
            evidence["board_sha256"],
            hashlib.sha256(b"board").hexdigest(),
        )
        self.assertEqual(
            evidence["board_integrity"],
            {
                "sha256_before": hashlib.sha256(b"board").hexdigest(),
                "sha256_after": hashlib.sha256(b"board").hexdigest(),
                "equal": True,
            },
        )
        self.assertFalse(any(name == "save_project" for name, _ in client.calls))

    def test_drc_accepts_exact_23_connector_endpoints_and_normalizes_nets(self):
        evidence = self.require_drc_report(
            connector_drc_report(
                unrelated_unconnected=(
                    "    @(90.0000 mm, 91.0000 mm): PTH pad 2 [/ROW0] of SW1",
                )
            )
        )

        self.assertEqual(
            evidence["connector_unconnected_endpoints"],
            [
                {"reference": reference, "pad_number": pad_number, "net": net}
                for reference, pad_number, net in EXPECTED_CONNECTOR_ENDPOINTS
            ],
        )

    def test_drc_ignores_j_like_net_on_unrelated_reference(self):
        evidence = self.require_drc_report(
            connector_drc_report(
                unrelated_unconnected=(
                    "    @(90.0000 mm, 91.0000 mm): PTH pad 1 [/J1] of TP1",
                )
            )
        )

        self.assertEqual(len(evidence["connector_unconnected_endpoints"]), 23)

    def test_drc_rejects_missing_connector_endpoint(self):
        endpoints = tuple(
            endpoint
            for endpoint in EXPECTED_CONNECTOR_ENDPOINTS
            if endpoint != ("J4", "3", "ROW2")
        )

        with self.assertRaisesRegex(RuntimeError, "missing.*J4.*3.*ROW2"):
            self.require_drc_report(connector_drc_report(endpoints))

    def test_drc_rejects_duplicate_connector_endpoint(self):
        endpoints = EXPECTED_CONNECTOR_ENDPOINTS + (("J1", "1", "VSYS"),)

        with self.assertRaisesRegex(RuntimeError, "duplicate.*J1.*1.*VSYS"):
            self.require_drc_report(connector_drc_report(endpoints))

    def test_drc_rejects_wrong_connector_net(self):
        endpoints = tuple(
            ("J2", "1", "COL9") if endpoint == ("J2", "1", "COL0") else endpoint
            for endpoint in EXPECTED_CONNECTOR_ENDPOINTS
        )

        with self.assertRaisesRegex(RuntimeError, "unexpected.*J2.*1.*COL9"):
            self.require_drc_report(connector_drc_report(endpoints))

    def test_drc_rejects_unexpected_connector_pad(self):
        endpoints = EXPECTED_CONNECTOR_ENDPOINTS + (("J1", "4", "VSYS"),)

        with self.assertRaisesRegex(RuntimeError, "unexpected.*J1.*4.*VSYS"):
            self.require_drc_report(connector_drc_report(endpoints))

    def test_drc_rejects_unexpected_connector_reference(self):
        endpoints = EXPECTED_CONNECTOR_ENDPOINTS + (("J7", "1", "DEBUG"),)

        with self.assertRaisesRegex(RuntimeError, "unexpected.*J7.*1.*DEBUG"):
            self.require_drc_report(connector_drc_report(endpoints))

    def test_drc_rejects_missing_endpoint_when_global_count_is_compensated(self):
        endpoints = tuple(
            endpoint
            for endpoint in EXPECTED_CONNECTOR_ENDPOINTS
            if endpoint != ("J6", "3", "GP29")
        )
        report = connector_drc_report(
            endpoints,
            unrelated_unconnected=(
                "    @(90.0000 mm, 91.0000 mm): PTH pad 1 [/COMPENSATION] of TP1",
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "missing.*J6.*3.*GP29"):
            self.require_drc_report(report, payload=drc_payload(unconnected=367))

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

    def test_acceptance_rejects_bool_and_nonfinite_pose_evidence(self):
        import tools.check_pcb_acceptance as checker

        malformed_poses = (
            ("x", (False, 36.0, 0.0, "B.Cu")),
            ("y", (282.5, False, 0.0, "B.Cu")),
            ("rotation", (282.5, 36.0, False, "B.Cu")),
            ("x", (float("nan"), 36.0, 0.0, "B.Cu")),
            ("y", (282.5, float("inf"), 0.0, "B.Cu")),
            ("rotation", (282.5, 36.0, float("-inf"), "B.Cu")),
        )

        for field, pose in malformed_poses:
            with self.subTest(field=field, value=pose):
                client = FakeClient()
                client.queue_json(
                    "get_component_list",
                    connector_component_inventory(pose_override={"J1": pose}),
                )
                with TemporaryDirectory() as directory:
                    board = Path(directory) / "lh60.kicad_pcb"
                    board.write_text("board")
                    with self.assertRaisesRegex(RuntimeError, f"J1 {field} mismatch"):
                        checker._require_connector_pose_and_graphics(client, board)

    def test_acceptance_rejects_duplicate_inventory_reference(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        inventory = connector_component_inventory()
        inventory["components"].append(deepcopy(inventory["components"][0]))
        inventory["count"] += 1
        client.queue_json("get_component_list", inventory)

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "duplicate component reference"):
                checker._require_exact_inventory(client, board)

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

    def test_acceptance_rejects_unexpected_j_related_drc_report_findings(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("run_drc", drc_payload())

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            report = drc_report_text(
                ("clearance", ["@(1.0000 mm, 2.0000 mm): Footprint text of J1"]),
            )

            def fake_run(command, check, capture_output, text):
                self.assertEqual(command[1:3], ["pcb", "drc"])
                (root / "drc.rpt").write_text(report)
                return mock.Mock(stdout="", stderr="", returncode=0)

            with mock.patch.object(checker.subprocess, "run", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "unexpected J-related DRC report finding"):
                    checker._require_drc(client, board, root, kicad_cli=Path("kicad-cli"))

    def test_non_unconnected_drc_rejects_footprint_j1_item(self):
        import tools.check_pcb_acceptance as checker

        report = drc_report_text(
            ("courtyards_overlap", ["@(1.0000 mm, 2.0000 mm): Footprint J1"]),
        )

        self.assertEqual(
            checker._check_report_for_unexpected_connector_findings(report),
            [
                {
                    "rule": "courtyards_overlap",
                    "line": "@(1.0000 mm, 2.0000 mm): Footprint J1",
                }
            ],
        )

    def test_non_unconnected_drc_rejects_unexpected_footprint_j7_item(self):
        import tools.check_pcb_acceptance as checker

        report = drc_report_text(
            ("courtyards_overlap", ["@(1.0000 mm, 2.0000 mm): Footprint J7"]),
        )

        self.assertEqual(
            checker._check_report_for_unexpected_connector_findings(report),
            [
                {
                    "rule": "courtyards_overlap",
                    "line": "@(1.0000 mm, 2.0000 mm): Footprint J7",
                }
            ],
        )

    def test_non_unconnected_drc_ignores_j_like_net_on_non_connector_item(self):
        import tools.check_pcb_acceptance as checker

        report = drc_report_text(
            (
                "clearance",
                ["@(1.0000 mm, 2.0000 mm): Pad 1 [/J1_SIGNAL] of U1 on F.Cu"],
            ),
        )

        self.assertEqual(
            checker._check_report_for_unexpected_connector_findings(report),
            [],
        )

    def test_acceptance_rejects_drc_counter_drift(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("run_drc", drc_payload(total=531))

        with TemporaryDirectory() as directory:
            board = Path(directory) / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "DRC total_violations mismatch"):
                checker._require_drc(client, board, Path(directory), kicad_cli=Path("kicad-cli"))

    def test_acceptance_rejects_missing_drc_report(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        client.queue_json("run_drc", drc_payload())

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            with mock.patch.object(checker.subprocess, "run", return_value=mock.Mock(returncode=0)):
                with self.assertRaisesRegex(RuntimeError, "DRC report missing"):
                    checker._require_drc(client, board, root, kicad_cli=Path("kicad-cli"))

    def test_acceptance_rejects_existing_drc_report_before_export(self):
        import tools.check_pcb_acceptance as checker

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            (root / "drc.rpt").write_text("stale report")
            with mock.patch.object(checker.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "DRC report output already exists"):
                    checker._write_drc_report(board, root, kicad_cli=Path("kicad-cli"))
                run.assert_not_called()

    def test_acceptance_rejects_position_export_with_connectors(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient(position_csv="Ref,Val\nJ1,PWR\n")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "position export must exclude J1"):
                checker._require_position_export_without_connectors(client, board, root / "positions.csv")

    def test_acceptance_rejects_position_export_without_ref_column(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient(position_csv="Designator,Val\nU1,MCU\n")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            with self.assertRaisesRegex(RuntimeError, "position export must contain Ref column"):
                checker._require_position_export_without_connectors(client, board, root / "positions.csv")

    def test_acceptance_ignores_connector_names_outside_ref_column(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient(position_csv="Ref,Val,Package\nU1,J1 regulator,J2-body\n")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            evidence = checker._require_position_export_without_connectors(
                client, board, root / "positions.csv"
            )

        self.assertEqual(evidence["rows"], 1)

    def test_acceptance_rejects_existing_position_output_before_export(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient(export_should_write=False)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            output = root / "positions.csv"
            output.write_text("Ref,Val\nU1,stale\n")
            with self.assertRaisesRegex(RuntimeError, "position output already exists"):
                checker._require_position_export_without_connectors(client, board, output)
        self.assertFalse(any(name == "export_position_file" for name, _ in client.calls))

    def test_acceptance_rejects_missing_svg_output(self):
        import tools.check_pcb_acceptance as checker

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            with mock.patch.object(checker.subprocess, "run", return_value=mock.Mock(returncode=0)):
                with self.assertRaisesRegex(RuntimeError, "back SVG export missing"):
                    checker._export_back_svg(board, root / "back.svg", kicad_cli=Path("kicad-cli"))

    def test_acceptance_rejects_existing_svg_output_before_export(self):
        import tools.check_pcb_acceptance as checker

        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board")
            output = root / "back.svg"
            output.write_text("<svg>stale</svg>")
            with mock.patch.object(checker.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "back SVG output already exists"):
                    checker._export_back_svg(board, output, kicad_cli=Path("kicad-cli"))
                run.assert_not_called()

    def test_acceptance_rejects_board_hash_drift_after_queries_and_exports(self):
        import tools.check_pcb_acceptance as checker

        client = FakeClient()
        queue_happy_path(client)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            board = root / "lh60.kicad_pcb"
            board.write_text("board before")
            report = connector_drc_report()
            original_call_tool = client.call_tool
            mutated = False

            def mutating_call_tool(name, arguments):
                nonlocal mutated
                if not mutated:
                    board.write_text("board after")
                    mutated = True
                return original_call_tool(name, arguments)

            client.call_tool = mutating_call_tool

            def fake_run(command, check, capture_output, text):
                if command[1:3] == ["pcb", "drc"]:
                    (root / "drc.rpt").write_text(report)
                else:
                    (root / "back.svg").write_text("<svg/>")
                return mock.Mock(stdout="", stderr="", returncode=0)

            with mock.patch.object(checker, "_git_sha", return_value="a" * 40), mock.patch.object(
                checker.subprocess,
                "run",
                side_effect=fake_run,
            ):
                with self.assertRaisesRegex(RuntimeError, "board changed during acceptance"):
                    checker.acceptance_record(
                        client,
                        board,
                        output_dir=root,
                        kicad_cli=Path("kicad-cli"),
                    )


if __name__ == "__main__":
    unittest.main()
