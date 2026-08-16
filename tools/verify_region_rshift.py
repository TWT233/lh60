from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import unittest


class RShiftProductionReportTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    REPORT_PATH = ROOT / "docs" / "regions" / "rshift.json"
    EXPECTED_SOCKET_IDS = (
        "r3_rshift_left_1.75u",
        "r3_rshift_right_fn_1u",
        "r3_rshift_left_fn_1u",
        "r3_rshift_right_1.75u",
    )

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(cls.REPORT_PATH.read_text())

    def region(self):
        from tools.lh60_design.layout import REGION_ROTATIONS_DEG, physical_keys
        from tools.lh60_design.regions import RegionPlacement, RegionSpec

        keys = {
            key.physical_key_id: key
            for key in physical_keys()
            if key.region == "rshift"
        }
        return RegionSpec(
            region="rshift",
            placements=tuple(
                RegionPlacement(
                    socket_ref=key_id,
                    footprint=(
                        "Gateron-LP-Hotswap-Socket-"
                        f"{keys[key_id].footprint_size}"
                    ),
                    center_x_mm=keys[key_id].center_x_mm,
                    center_y_mm=keys[key_id].center_y_mm,
                    logical_node_id=keys[key_id].logical_node_id,
                    allowed_rotations_deg=REGION_ROTATIONS_DEG["rshift"],
                )
                for key_id in self.EXPECTED_SOCKET_IDS
            ),
        )

    def test_report_is_solved_and_retires_the_2_75u_layout(self):
        self.assertEqual(
            set(self.payload),
            {
                "schema_version",
                "region",
                "status",
                "solved",
                "retired_socket_refs",
                "placements",
                "minimum_copper_clearance_mm",
                "minimum_hole_edge_clearance_mm",
                "minimum_courtyard_clearance_mm",
                "hole_edge_target_met",
                "drc_status",
                "blocking_conflicts",
            },
        )
        self.assertEqual(self.payload["schema_version"], 2)
        self.assertEqual(self.payload["region"], "rshift")
        self.assertEqual(self.payload["status"], "solved")
        self.assertTrue(self.payload["solved"])
        self.assertEqual(
            self.payload["retired_socket_refs"],
            ["r3_rshift_2.75u"],
        )
        self.assertNotIn("r3_rshift_2.75u", json.dumps(self.payload["placements"]))

    def test_solver_recomputes_the_four_socket_solution(self):
        from tools.lh60_design.regions import solve_region

        expected = solve_region(self.region())

        self.assertTrue(expected.solved)
        self.assertEqual(
            self.payload["placements"],
            [placement.to_dict() for placement in expected.placements],
        )
        self.assertEqual(
            self.payload["minimum_copper_clearance_mm"],
            expected.minimum_copper_clearance_mm,
        )
        self.assertEqual(
            self.payload["minimum_hole_edge_clearance_mm"],
            expected.minimum_hole_edge_clearance_mm,
        )
        self.assertEqual(
            self.payload["minimum_courtyard_clearance_mm"],
            expected.minimum_courtyard_clearance_mm,
        )
        self.assertEqual(
            self.payload["hole_edge_target_met"],
            expected.hole_edge_target_met,
        )
        self.assertEqual(self.payload["drc_status"], "geometry-pass")
        self.assertEqual(self.payload["blocking_conflicts"], [])
        self.assertEqual(
            tuple(
                (placement["socket_ref"], placement["rotation_deg"])
                for placement in self.payload["placements"]
            ),
            (
                ("r3_rshift_left_1.75u", 180),
                ("r3_rshift_right_fn_1u", 180),
                ("r3_rshift_left_fn_1u", 0),
                ("r3_rshift_right_1.75u", 0),
            ),
        )

    def test_production_board_matches_the_report(self):
        from tools.lh60_design.pcb import BOARD, read_board_placements
        from tools.lh60_design.schematic import switch_references

        placements = read_board_placements(BOARD)
        references = switch_references()

        self.assertNotIn("SW59", placements)
        for placement in self.payload["placements"]:
            reference = references[placement["socket_ref"]]
            x, y, rotation, layer = placements[reference]
            self.assertAlmostEqual(x, placement["center_x_mm"])
            self.assertAlmostEqual(y, placement["center_y_mm"])
            self.assertAlmostEqual(
                rotation % 360,
                placement["rotation_deg"] % 360,
            )
            self.assertEqual(layer, "F.Cu")



if __name__ == "__main__":
    unittest.main()
