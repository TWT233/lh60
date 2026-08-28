import json
from pathlib import Path
import unittest


class ProductionRegionReportTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    REGION_IDS = ("top-right", "enter", "lshift", "rshift")
    EXPECTED_SOCKET_IDS = {
        "top-right": (
            "r0_top_2u",
            "r0_top_split_left_fn_1u",
            "r0_top_split_right_1u",
        ),
        "enter": (
            "r2_enter_ansi_2.25u",
            "r2_enter_split_left_fn_1u",
            "r2_enter_split_right_1.25u",
        ),
        "lshift": (
            "r3_lshift_split_left_fn_1u",
            "r3_lshift_2.25u",
            "r3_lshift_split_1.25u",
        ),
        "rshift": (
            "r3_rshift_left_1.75u",
            "r3_rshift_right_fn_1u",
            "r3_rshift_left_fn_1u",
            "r3_rshift_right_1.75u",
        ),
    }

    def report(self, region):
        return json.loads(
            (self.ROOT / "docs" / "regions" / f"{region}.json").read_text()
        )

    def test_every_active_region_matches_layout_board_and_geometry(self):
        from tools.lh60_design.layout import physical_keys
        from tools.lh60_design.pcb import BOARD, read_board_placements
        from tools.lh60_design.regions import (
            RegionPlacement,
            _blocking_conflicts,
            measure_clearances,
        )
        from tools.lh60_design.schematic import switch_references

        keys = {key.physical_key_id: key for key in physical_keys()}
        board = read_board_placements(BOARD)
        references = switch_references()

        self.assertEqual(
            {path.stem for path in (self.ROOT / "docs" / "regions").glob("*.json")},
            set(self.REGION_IDS),
        )
        for region in self.REGION_IDS:
            with self.subTest(region=region):
                report = self.report(region)
                expected_ids = self.EXPECTED_SOCKET_IDS[region]
                self.assertEqual(
                    set(report),
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
                self.assertEqual(report["schema_version"], 2)
                self.assertEqual(report["region"], region)
                self.assertEqual(report["status"], "solved")
                self.assertTrue(report["solved"])
                self.assertEqual(report["drc_status"], "geometry-pass")
                self.assertEqual(report["blocking_conflicts"], [])
                self.assertEqual(
                    tuple(
                        placement["socket_ref"]
                        for placement in report["placements"]
                    ),
                    expected_ids,
                )
                placements = []
                for item in report["placements"]:
                    key = keys[item["socket_ref"]]
                    reference = references[item["socket_ref"]]
                    x, y, rotation, layer = board[reference]
                    self.assertAlmostEqual(x, key.center_x_mm)
                    self.assertAlmostEqual(y, key.center_y_mm)
                    self.assertAlmostEqual(
                        rotation % 360,
                        item["rotation_deg"] % 360,
                    )
                    self.assertEqual(layer, "F.Cu")
                    self.assertEqual(
                        item["logical_node_id"],
                        key.logical_node_id,
                    )
                    placements.append(
                        RegionPlacement(
                            socket_ref=item["socket_ref"],
                            footprint=item["footprint"],
                            center_x_mm=item["center_x_mm"],
                            center_y_mm=item["center_y_mm"],
                            logical_node_id=item["logical_node_id"],
                            rotation_deg=item["rotation_deg"],
                        )
                    )

                clearance = measure_clearances(placements)
                self.assertEqual(_blocking_conflicts(clearance), ())
                self.assertEqual(
                    report["minimum_copper_clearance_mm"],
                    clearance.minimum_copper_clearance_mm,
                )
                self.assertEqual(
                    report["minimum_hole_edge_clearance_mm"],
                    clearance.minimum_hole_edge_clearance_mm,
                )
                self.assertEqual(
                    report["minimum_courtyard_clearance_mm"],
                    clearance.minimum_courtyard_clearance_mm,
                )
                self.assertEqual(
                    report["hole_edge_target_met"],
                    clearance.minimum_hole_edge_clearance_mm >= 0.5,
                )


if __name__ == "__main__":
    unittest.main()
