import json
import shutil
import unittest
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def mcp_client():
    from tools.lh60_design.mcp import McpClient

    client = McpClient(
        Path.home() / ".local/bin/konnect",
        Path.home() / ".config/konnect/config.toml",
    )
    try:
        yield client
    finally:
        client.close()
        if client.process.stdin:
            client.process.stdin.close()
        if client.process.stdout:
            client.process.stdout.close()


class ProjectContractTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    PROJECT_DIR = Path("/tmp/lh60-project-contract")

    def setUp(self):
        shutil.rmtree(self.PROJECT_DIR, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self.PROJECT_DIR, ignore_errors=True)

    def generate(self):
        from tools.lh60_design.project import create_production_project

        self.PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        library_root = self.PROJECT_DIR / "lib"
        library_root.mkdir(exist_ok=True)
        core_root = library_root / "lh60-core"
        core_footprints = core_root / "lh60-core.pretty"
        core_symbols = core_root / "lh60-core.kicad_sym"
        socket_library = library_root / "lh60-sockets"
        socket_library.mkdir(exist_ok=True)
        interconnect_root = library_root / "lh60-interconnect"
        interconnect_footprints = interconnect_root / "lh60-interconnect.pretty"
        interconnect_symbols = interconnect_root / "lh60-interconnect.kicad_sym"
        core_footprints.mkdir(parents=True, exist_ok=True)
        interconnect_footprints.mkdir(parents=True, exist_ok=True)
        with mcp_client() as client:
            client.tool_schemas("library")
            fixture_socket = socket_library / "Gateron-LP-Hotswap-Socket-1U.kicad_mod"
            if not fixture_socket.exists():
                client.call_tool(
                    "create_footprint",
                    {
                        "output": str(fixture_socket),
                        "name": "Gateron-LP-Hotswap-Socket-1U",
                        "pads": [
                            {
                                "number": "1",
                                "type": "thru_hole",
                                "shape": "circle",
                                "x": 0,
                                "y": 0,
                                "width": 2,
                                "height": 2,
                                "drill": 1,
                            }
                        ],
                    },
                )
            if not core_symbols.exists():
                client.call_tool(
                    "create_symbol",
                    {
                        "library_path": str(core_symbols),
                        "name": "PowerFlag",
                        "reference_prefix": "#PWR",
                        "value": "PWR_FLAG",
                        "pins": [
                            {
                                "number": "1",
                                "name": "PWR_FLAG",
                                "type": "power_out",
                                "x": 7.62,
                                "y": 0,
                                "angle": 180,
                                "length": 2.54,
                            }
                        ],
                    },
                )
            if not interconnect_symbols.exists():
                client.call_tool(
                    "create_symbol",
                    {
                        "library_path": str(interconnect_symbols),
                        "name": "FPC-05F-24PH20",
                        "reference_prefix": "J",
                        "value": "FPC-05F-24PH20",
                        "pins": [
                            {
                                "number": "1",
                                "name": "1",
                                "type": "passive",
                                "x": 7.62,
                                "y": 0,
                                "angle": 180,
                                "length": 2.54,
                            }
                        ],
                    },
                )
            fixture_core_footprint = core_footprints / "PinHeader_1x03_P2.54mm_Vertical.kicad_mod"
            if not fixture_core_footprint.exists():
                client.call_tool(
                    "create_footprint",
                    {
                        "output": str(fixture_core_footprint),
                        "name": "PinHeader_1x03_P2.54mm_Vertical",
                        "pads": [
                            {
                                "number": "1",
                                "type": "thru_hole",
                                "shape": "rect",
                                "x": 0,
                                "y": 0,
                                "width": 1,
                                "height": 1,
                                "drill": 0.6,
                            }
                        ],
                    },
                )
            fixture_interconnect_footprint = interconnect_footprints / "FPC-05F-24PH20.kicad_mod"
            if not fixture_interconnect_footprint.exists():
                client.call_tool(
                    "create_footprint",
                    {
                        "output": str(fixture_interconnect_footprint),
                        "name": "FPC-05F-24PH20",
                        "pads": [
                            {
                                "number": "1",
                                "type": "smd",
                                "shape": "rect",
                                "x": 0,
                                "y": 0,
                                "width": 1,
                                "height": 1,
                            }
                        ],
                    },
                )
            create_production_project(client, self.PROJECT_DIR)

    def test_refuses_a_partial_existing_project(self):
        from tools.lh60_design.project import create_production_project

        self.PROJECT_DIR.mkdir(parents=True)
        (self.PROJECT_DIR / "lh60.kicad_pro").touch()

        with self.assertRaisesRegex(RuntimeError, "partial existing project"):
            create_production_project(None, self.PROJECT_DIR)

    def test_generates_blank_portable_project_with_approved_rules(self):
        self.generate()

        project = self.PROJECT_DIR / "lh60.kicad_pro"
        schematic = self.PROJECT_DIR / "lh60.kicad_sch"
        board = self.PROJECT_DIR / "lh60.kicad_pcb"
        self.assertTrue(project.is_file())
        self.assertTrue(schematic.is_file())
        self.assertTrue(board.is_file())

        footprint_table = (self.PROJECT_DIR / "fp-lib-table").read_text()
        symbol_table = (self.PROJECT_DIR / "sym-lib-table").read_text()
        self.assertIn(
            '${KIPRJMOD}/lib/lh60-sockets',
            footprint_table,
        )
        self.assertIn(
            '${KIPRJMOD}/lib/lh60-core/lh60-core.pretty',
            footprint_table,
        )
        self.assertIn(
            '${KIPRJMOD}/lib/lh60-interconnect/lh60-interconnect.pretty',
            footprint_table,
        )
        self.assertIn(
            '${KIPRJMOD}/lib/lh60-core/lh60-core.kicad_sym',
            symbol_table,
        )
        self.assertIn(
            '${KIPRJMOD}/lib/lh60-interconnect/lh60-interconnect.kicad_sym',
            symbol_table,
        )
        self.assertNotIn('lh60-mcu', footprint_table)
        self.assertNotIn('lh60-mcu', symbol_table)
        self.assertNotIn(str(Path.cwd()), footprint_table + symbol_table)

        with mcp_client() as client:
            client.tool_schemas("verification")
            client.tool_schemas("pcb_board")
            rules = client.call_tool(
                "get_design_rules",
                {"board": str(board)},
            )
            extents = client.call_tool(
                "get_board_extents",
                {"board": str(board)},
            )
            info = client.call_tool(
                "get_project_info",
                {"path": str(project)},
            )

        rule_text = rules["content"][0]["text"]
        rule_values = json.loads(rule_text)["rules"]
        self.assertEqual(
            rule_values,
            {
                "min_clearance": 0.25,
                "min_trace_width": 0.25,
                "min_via_drill": 0.3,
                "min_via_size": 0.7,
                "min_hole_to_hole": 0.45,
            },
        )
        self.assertIn("lh60.kicad_sch", json.dumps(info))
        self.assertIn("lh60.kicad_pcb", json.dumps(info))

        extent_text = json.dumps(extents, sort_keys=True)
        self.assertIn("285.75", extent_text)
        self.assertIn("95.25", extent_text)

        board_text = board.read_text()
        custom_rules = (self.PROJECT_DIR / "lh60.kicad_dru").read_text()
        self.assertNotIn("(min_clearance ", board_text)
        self.assertNotIn("(rule ", board_text)
        for layer in ("F.Cu", "B.Cu"):
            self.assertIn(f'(rule "konnect:{layer}:clearance"', custom_rules)
            self.assertIn(f'(rule "konnect:{layer}:track_width"', custom_rules)
        self.assertNotIn("(footprint ", board_text)
        self.assertNotIn("(segment ", board_text)
        self.assertNotIn("(zone ", board_text)
        self.assertNotIn("lh60-mcu", board_text)

    def test_generator_is_idempotent_for_a_complete_project(self):
        self.generate()
        project = self.PROJECT_DIR / "lh60.kicad_pro"
        first_project_bytes = project.read_bytes()

        self.generate()

        self.assertEqual(project.read_bytes(), first_project_bytes)
        self.assertTrue((self.PROJECT_DIR / "lh60.kicad_sch").is_file())
        self.assertTrue((self.PROJECT_DIR / "lh60.kicad_pcb").is_file())


class ProjectConfigTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_project_config_records_approved_fabrication_constraints(self):
        config = json.loads(
            (self.ROOT / ".konnect" / "project.json").read_text()
        )

        self.assertEqual(config["fab_constraints"]["fab_house"], "JLCPCB")
        self.assertEqual(config["fab_constraints"]["layer_count"], 2)
        self.assertEqual(config["fab_constraints"]["min_trace_width_mm"], 0.25)
        self.assertEqual(config["fab_constraints"]["min_clearance_mm"], 0.25)
        self.assertEqual(config["fab_constraints"]["min_via_drill_mm"], 0.3)
        self.assertEqual(config["pcb"]["via_diameter_mm"], 0.7)
        self.assertEqual(config["pcb"]["power_trace_width_mm"], 0.5)
        self.assertEqual(config["pcb"]["copper_to_edge_mm"], 0.5)
        self.assertEqual(config["pcb"]["hole_edge_target_mm"], 0.5)
        self.assertEqual(config["pcb"]["hole_edge_hard_minimum_mm"], 0.45)


if __name__ == "__main__":
    unittest.main()
